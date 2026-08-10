"""
Conector PrestaShop · Implementación operativa (Fase WEB-17). Mismo patrón que WooCommerce/Shopify: extiende
el conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/pedidos/stock). Toda
la lógica específica de PrestaShop vive aquí. Idempotente, multiempresa, degradable.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    PrestaShopConnector as _PrestaPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.prestashop import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.prestashop import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.prestashop import \
    transporte as T

logger = logging.getLogger("marketplace.integraciones_comerciales.prestashop.adaptador")


def _num(v, defecto=0.0):
    try:
        return float(v)
    except Exception:
        return defecto


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
    except Exception:
        return None


def _texto(v):
    """PrestaShop devuelve campos traducibles como str o como lista [{id, value}]. Normaliza a str."""
    if isinstance(v, list) and v:
        first = v[0]
        return (first.get("value") if isinstance(first, dict) else str(first)) or ""
    if isinstance(v, dict):
        return v.get("value") or ""
    return v if v is not None else ""


class PrestaShopAdapter(_PrestaPreparado):
    """Conector PrestaShop operativo. Instanciable sin argumentos (`motor.adaptador('prestashop')`)."""

    plataforma = "prestashop"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "PRESTASHOP"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _url_integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "prestashop") if id_empresa is not None else None
            return i.get("url") if i else None
        except Exception:
            return None

    def _config(self, id_empresa=None):
        url = self._url or self._url_integracion(id_empresa) or os.getenv("PRESTASHOP_URL")
        return url, S.api_key(self._credenciales_ref)

    def disponible(self, id_empresa=None) -> bool:
        url, key = self._config(id_empresa)
        return bool(url and key)

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["estado"] = "OPERATIVO" if self.disponible() else "PREPARADO"
        return d

    def _audit(self, evento, id_empresa=None, usuario=None, detalle=None):
        A.registrar(evento, id_empresa=id_empresa, usuario=usuario, detalle=detalle)

    def _req(self, method, path, id_empresa=None, *, json=None, params=None):
        url, key = self._config(id_empresa)
        if not (url and key):
            raise IntegracionError(CodigoError.MISSING_CREDENTIALS,
                                   "Shop URL/API Key de PrestaShop no configurados", plataforma="prestashop")
        return T.get_transporte().request(method, url, path, api_key=key, json=json, params=params)

    def _paginar(self, recurso, id_empresa, *, extra=None, count=100, max_paginas=50):
        """Paginación PrestaShop por `limit=offset,count`. Extrae la lista `recurso` de la respuesta."""
        out = []
        for page in range(max_paginas):
            params = {"display": "full", "limit": f"{page * count},{count}"}
            if extra:
                params.update(extra)
            data = self._req("GET", recurso, id_empresa, params=params)
            items = data.get(recurso, []) if isinstance(data, dict) else (data or [])
            if not items:
                break
            out.extend(items)
            if len(items) < count:
                break
        return out

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.PRESTA_AUTH, id_empresa, usuario)
        url, key = self._config(id_empresa)
        if not (url and key):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales PrestaShop"}
        try:
            self._req("GET", "products", id_empresa, params={"limit": "0,1"})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.PRESTA_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.PRESTA_VALIDATE, id_empresa, usuario)
        url, key = self._config(id_empresa)
        comprob = {"url": "ok" if url else "falta", "api_key": "ok" if key else "falta",
                   "ssl": "ok" if (url or "").lower().startswith("https") else "aviso"}
        if not (url and key):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "products", id_empresa, params={"limit": "0,1"})
            version = self.obtener_version(id_empresa=id_empresa)
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "prestashop", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar presta: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.PRESTA_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        try:
            data = self._req("GET", "configurations", id_empresa,
                             params={"filter[name]": "PS_VERSION_DB", "display": "full"})
            cfgs = data.get("configurations", []) if isinstance(data, dict) else []
            if cfgs:
                return _texto(cfgs[0].get("value"))
        except Exception:
            pass
        return None

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.PRESTA_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        extra = {"date": "1", "filter[date_upd]": f"[{_iso(desde)},{_iso(time.time())}]"} if desde else None
        procesados, skus = 0, []
        for p in self._paginar("products", id_empresa, extra=extra):
            sku = (str(p.get("reference") or "").strip()) or f"PRESTA-{p.get('id')}"
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=_texto(p.get("name")))
                from src.db import articulos as ART
                ART.actualizar_precio(sku, _num(p.get("price")))
            except Exception as e:
                logger.debug("upsert producto presta %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.PRESTA_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        extra = {"date": "1", "filter[date_upd]": f"[{_iso(desde)},{_iso(time.time())}]"} if desde else None
        creados = actualizados = 0
        for c in self._paginar("customers", id_empresa, extra=extra):
            email = (c.get("email") or "").strip()
            nombre = " ".join(x for x in (c.get("firstname"), c.get("lastname")) if x).strip() or email
            try:
                existente = None
                if email:
                    for r in (CL.buscar_clientes(email) or []):
                        if str(r.get("email", "")).lower() == email.lower():
                            existente = r
                            break
                if existente:
                    CL.actualizar_cliente(existente.get("id"), telefono=c.get("phone"))
                    actualizados += 1
                else:
                    CL.crear_cliente(nombre, email=email or None, telefono=c.get("phone"))
                    creados += 1
            except Exception as e:
                logger.debug("importar cliente presta %s: %s", email, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.PRESTA_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        extra = {"date": "1", "filter[date_upd]": f"[{_iso(desde)},{_iso(time.time())}]"} if desde else None
        creados = duplicados = 0
        for o in self._paginar("orders", id_empresa, extra=extra):
            ref = f"PRESTA-{o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            filas = ((o.get("associations") or {}).get("order_rows")) or []
            lineas = [{"codigo": (r.get("product_reference") or f"PRESTA-{r.get('product_id')}"),
                       "nombre": _texto(r.get("product_name")), "cantidad": _num(r.get("product_quantity"), 1),
                       "precio": _num(r.get("unit_price_tax_incl"))} for r in filas]
            if not lineas:
                continue
            cliente = {"nombre": (o.get("customer_name") or f"Cliente {o.get('id_customer') or 'Web'}"),
                       "email": o.get("email"), "telefono": None}
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="prestashop", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido presta %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.PRESTA_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            pid = it.get("presta_id") or it.get("id")
            if not pid:
                continue
            stock = SA.stock_total_global(it.get("sku"), id_empresa=id_empresa) if it.get("sku") else 0
            try:
                self._req("PUT", f"stock_availables/{it.get('stock_id', pid)}", id_empresa,
                          json={"stock_available": {"id": it.get("stock_id", pid), "quantity": int(stock)}})
                n += 1
            except Exception as e:
                logger.debug("exportar stock presta %s: %s", pid, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.PRESTA_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            pid = it.get("presta_id") or it.get("id")
            precio = it.get("precio")
            if not pid or precio is None:
                continue
            try:
                self._req("PUT", f"products/{pid}", id_empresa,
                          json={"product": {"id": pid, "price": str(_num(precio))}})
                n += 1
            except Exception as e:
                logger.debug("exportar precio presta %s: %s", pid, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → PrestaShop) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        pid = str(id_externo).replace("PRESTA-", "")
        try:
            self._req("PUT", f"orders/{pid}", id_empresa,
                      json={"order": {"id": pid, "note": f"estado ERP: {estado_erp}"}})
            return {"ok": True, "estado_erp": str(estado_erp)}
        except IntegracionError as e:
            self._audit(A.PRESTA_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.PRESTA_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "prestashop", usuario=usuario)
            servicio.sincronizar(id_empresa, "prestashop", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync presta: %s", e)
        self._audit(A.PRESTA_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.PRESTA_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "prestashop") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "prestashop", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc presta: %s", e)
        self._audit(A.PRESTA_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
