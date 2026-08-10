"""
Conector OpenCart · Implementación operativa (Fase WEB-19). Mismo patrón que WooCommerce/Shopify/PrestaShop/
Magento: extiende el conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/
pedidos/stock). Toda la lógica específica de OpenCart vive aquí. Idempotente, multiempresa, degradable.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    OpenCartConnector as _OpenCartPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.opencart import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.opencart import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.opencart import \
    transporte as T

logger = logging.getLogger("marketplace.integraciones_comerciales.opencart.adaptador")


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


class OpenCartAdapter(_OpenCartPreparado):
    """Conector OpenCart operativo. Instanciable sin argumentos (`motor.adaptador('opencart')`)."""

    plataforma = "opencart"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "OPENCART"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _url_integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "opencart") if id_empresa is not None else None
            return i.get("url") if i else None
        except Exception:
            return None

    def _config(self, id_empresa=None):
        url = self._url or self._url_integracion(id_empresa) or os.getenv("OPENCART_URL")
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
                                   "Shop URL/API Key de OpenCart no configurados", plataforma="opencart")
        return T.get_transporte().request(method, url, path, api_key=key, json=json, params=params)

    @staticmethod
    def _items(data, recurso):
        """OpenCart devuelve {recurso:[...]} o {'data':[...]} o una lista directa."""
        if isinstance(data, dict):
            return data.get(recurso) or data.get("data") or []
        return data or []

    def _paginar(self, recurso, id_empresa, *, extra=None, limit=100, max_paginas=50):
        out = []
        for page in range(1, max_paginas + 1):
            params = {"limit": limit, "page": page}
            if extra:
                params.update(extra)
            items = self._items(self._req("GET", recurso, id_empresa, params=params), recurso)
            if not items:
                break
            out.extend(items)
            if len(items) < limit:
                break
        return out

    def _incremental(self, desde):
        return {"filter_date_modified": _iso(desde)} if desde else None

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.OPENCART_AUTH, id_empresa, usuario)
        url, key = self._config(id_empresa)
        if not (url and key):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales OpenCart"}
        try:
            self._req("GET", "products", id_empresa, params={"limit": 1, "page": 1})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.OPENCART_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.OPENCART_VALIDATE, id_empresa, usuario)
        url, key = self._config(id_empresa)
        comprob = {"url": "ok" if url else "falta", "api_key": "ok" if key else "falta",
                   "ssl": "ok" if (url or "").lower().startswith("https") else "aviso"}
        if not (url and key):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "products", id_empresa, params={"limit": 1, "page": 1})
            version = self.obtener_version(id_empresa=id_empresa)
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "opencart", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar opencart: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.OPENCART_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        try:
            return type(self).version.api_version
        except Exception:
            return None

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.OPENCART_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        procesados, skus = 0, []
        for p in self._paginar("products", id_empresa, extra=self._incremental(desde)):
            sku = (str(p.get("sku") or p.get("model") or "").strip()) or f"OPENCART-{p.get('product_id')}"
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=p.get("name"))
                from src.db import articulos as ART
                ART.actualizar_precio(sku, _num(p.get("price")))
            except Exception as e:
                logger.debug("upsert producto opencart %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.OPENCART_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        creados = actualizados = 0
        for c in self._paginar("customers", id_empresa, extra=self._incremental(desde)):
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
                    CL.actualizar_cliente(existente.get("id"), telefono=c.get("telephone"))
                    actualizados += 1
                else:
                    CL.crear_cliente(nombre, email=email or None, telefono=c.get("telephone"))
                    creados += 1
            except Exception as e:
                logger.debug("importar cliente opencart %s: %s", email, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.OPENCART_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for o in self._paginar("orders", id_empresa, extra=self._incremental(desde)):
            ref = f"OPENCART-{o.get('order_id') or o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            cliente = {"nombre": " ".join(x for x in (o.get("firstname"), o.get("lastname")) if x)
                       or (o.get("email") or "Cliente Web"), "email": o.get("email"),
                       "telefono": o.get("telephone")}
            filas = o.get("products") or o.get("order_products") or []
            lineas = [{"codigo": (li.get("sku") or li.get("model") or f"OPENCART-{li.get('product_id')}"),
                       "nombre": li.get("name"), "cantidad": _num(li.get("quantity"), 1),
                       "precio": _num(li.get("price"))} for li in filas]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="opencart", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido opencart %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (por product_id; solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.OPENCART_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            oid = it.get("oc_id") or it.get("product_id")
            if not oid:
                continue
            stock = SA.stock_total_global(it.get("sku"), id_empresa=id_empresa) if it.get("sku") else 0
            try:
                self._req("PUT", f"products/{oid}", id_empresa, json={"quantity": int(stock)})
                n += 1
            except Exception as e:
                logger.debug("exportar stock opencart %s: %s", oid, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.OPENCART_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            oid = it.get("oc_id") or it.get("product_id")
            precio = it.get("precio")
            if not oid or precio is None:
                continue
            try:
                self._req("PUT", f"products/{oid}", id_empresa, json={"price": _num(precio)})
                n += 1
            except Exception as e:
                logger.debug("exportar precio opencart %s: %s", oid, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → OpenCart) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        oid = str(id_externo).replace("OPENCART-", "")
        try:
            self._req("PUT", f"orders/{oid}", id_empresa, json={"note": f"estado ERP: {estado_erp}"})
            return {"ok": True, "estado_erp": str(estado_erp)}
        except IntegracionError as e:
            self._audit(A.OPENCART_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.OPENCART_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "opencart", usuario=usuario)
            servicio.sincronizar(id_empresa, "opencart", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync opencart: %s", e)
        self._audit(A.OPENCART_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.OPENCART_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "opencart") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "opencart", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc opencart: %s", e)
        self._audit(A.OPENCART_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
