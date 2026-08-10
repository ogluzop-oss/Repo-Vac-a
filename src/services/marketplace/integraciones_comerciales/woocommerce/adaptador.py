"""
Conector WooCommerce · Implementación operativa (Fase WEB-15).

`WooCommerceAdapter` extiende el conector PREPARADO del motor WEB-13 (hereda contratos/capacidades/versión) e
implementa: autenticar · validar · obtener_version · importar_productos/clientes/pedidos · exportar_stock/
precios · actualizar_estado_pedido · sincronizacion_inicial/incremental. REUTILIZA los motores del ERP
(catálogo/clientes/pedidos/stock) — no crea `PedidoWeb`/`PedidoWoo` ni duplica lógica. Idempotente (dedup por
SKU/email/referencia externa), multiempresa, degradable (sin credenciales → `MISSING_CREDENTIALS`, sin red).
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    WooCommerceConnector as _WooPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.woocommerce import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.woocommerce import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.woocommerce import \
    transporte as T

logger = logging.getLogger("marketplace.integraciones_comerciales.woocommerce.adaptador")

# Mapeo de estado ERP → estado WooCommerce (para actualizar_estado_pedido).
_ESTADO_ERP_A_WOO = {"PENDIENTE": "pending", "PAGADO": "processing", "PREPARANDO": "processing",
                     "ENVIADO": "completed", "ENTREGADO": "completed", "CANCELADO": "cancelled"}


def _num(v, defecto=0.0):
    try:
        return float(v)
    except Exception:
        return defecto


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(float(ts)))
    except Exception:
        return None


class WooCommerceAdapter(_WooPreparado):
    """Conector WooCommerce operativo. Instanciable sin argumentos (`motor.adaptador('woocommerce')`)."""

    plataforma = "woocommerce"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "WOO"
        self._url = url

    # ── Configuración / disponibilidad (honesto, per-empresa) ──
    def _url_integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "woocommerce") if id_empresa is not None else None
            return i.get("url") if i else None
        except Exception:
            return None

    def _config(self, id_empresa=None):
        url = self._url or self._url_integracion(id_empresa) or os.getenv("WOO_URL")
        ck, cs = S.credenciales(self._credenciales_ref)
        return url, ck, cs

    def disponible(self, id_empresa=None) -> bool:
        url, ck, cs = self._config(id_empresa)
        return bool(url and ck and cs)

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["estado"] = "OPERATIVO" if self.disponible() else "PREPARADO"
        return d

    def _audit(self, evento, id_empresa=None, usuario=None, detalle=None):
        A.registrar(evento, id_empresa=id_empresa, usuario=usuario, detalle=detalle)

    def _req(self, method, path, id_empresa=None, *, json=None, params=None):
        url, ck, cs = self._config(id_empresa)
        if not (url and ck and cs):
            raise IntegracionError(CodigoError.MISSING_CREDENTIALS,
                                   "credenciales/URL de WooCommerce no configuradas", plataforma="woocommerce")
        return T.get_transporte().request(method, url, path, ck=ck, cs=cs, json=json, params=params)

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.WOO_AUTH, id_empresa, usuario)
        url, ck, cs = self._config(id_empresa)
        if not (url and ck and cs):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales WooCommerce"}
        try:
            r = self._req("GET", "products", id_empresa, params={"per_page": 1})
            return {"ok": True, "muestra": len(r or [])}
        except IntegracionError as e:
            self._audit(A.WOO_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación (URL/API/credenciales/permisos/versión/SSL) ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.WOO_VALIDATE, id_empresa, usuario)
        url, ck, cs = self._config(id_empresa)
        comprob = {"url": "ok" if url else "falta",
                   "credenciales": "ok" if (ck and cs) else "falta",
                   "ssl": "ok" if (url or "").lower().startswith("https") else "aviso"}
        if not (url and ck and cs):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            st = self._req("GET", "system_status", id_empresa)
            version = ((st or {}).get("environment") or {}).get("version")
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            # Actualiza SOLO el estado existente del motor (→ VALIDADA), sin crear estados nuevos.
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "woocommerce", usuario=usuario)
            except Exception as e:
                logger.debug("estado validar woo: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.WOO_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        try:
            st = self._req("GET", "system_status", id_empresa)
            return ((st or {}).get("environment") or {}).get("version")
        except IntegracionError:
            return None

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None, por_pagina=100,
                           max_paginas=50) -> dict:
        self._audit(A.WOO_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        procesados, skus = 0, []
        for page in range(1, max_paginas + 1):
            params = {"per_page": por_pagina, "page": page}
            if desde:
                params["modified_after"] = _iso(desde)
            items = self._req("GET", "products", id_empresa, params=params) or []
            for p in items:
                # Relación por SKU si existe; si no, identificador de Smart Manager (WOO-<id>).
                sku = (p.get("sku") or "").strip() or f"WOO-{p.get('id')}"
                try:
                    C.upsert_producto(sku, id_empresa=id_empresa, nombre=p.get("name"))  # idempotente
                    from src.db import articulos as ART
                    ART.actualizar_precio(sku, _num(p.get("price")))
                except Exception as e:
                    logger.debug("upsert producto %s: %s", sku, e)
                procesados += 1
                skus.append(sku)
            if len(items) < por_pagina:
                break
        return {"ok": True, "procesados": procesados, "skus": skus}

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None, por_pagina=100,
                          max_paginas=50) -> dict:
        self._audit(A.WOO_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        creados = actualizados = 0
        for page in range(1, max_paginas + 1):
            params = {"per_page": por_pagina, "page": page}
            if desde:
                params["modified_after"] = _iso(desde)
            items = self._req("GET", "customers", id_empresa, params=params) or []
            for c in items:
                email = (c.get("email") or "").strip()
                nombre = " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x).strip() \
                    or c.get("username") or email
                existente = None
                try:
                    if email:
                        for r in (CL.buscar_clientes(email) or []):
                            if str(r.get("email", "")).lower() == email.lower():
                                existente = r
                                break
                    if existente:
                        CL.actualizar_cliente(existente.get("id"), telefono=c.get("billing", {}).get("phone"))
                        actualizados += 1
                    else:
                        CL.crear_cliente(nombre, email=email or None,
                                         telefono=(c.get("billing") or {}).get("phone"))
                        creados += 1
                except Exception as e:
                    logger.debug("importar cliente %s: %s", email, e)
            if len(items) < por_pagina:
                break
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None, por_pagina=100,
                         max_paginas=50) -> dict:
        self._audit(A.WOO_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for page in range(1, max_paginas + 1):
            params = {"per_page": por_pagina, "page": page}
            if desde:
                params["modified_after"] = _iso(desde)
            items = self._req("GET", "orders", id_empresa, params=params) or []
            for o in items:
                ref = f"WOO-{o.get('id')}"
                # Idempotencia: no reimportar un pedido ya existente (por referencia externa).
                existe = any(str(p.get("referencia_externa")) == ref
                             for p in (OS.listar_pedidos_online(texto=ref) or []))
                if existe:
                    duplicados += 1
                    continue
                bl = o.get("billing") or {}
                cliente = {"nombre": " ".join(x for x in (bl.get("first_name"), bl.get("last_name")) if x)
                           or "Cliente Web", "email": bl.get("email"), "telefono": bl.get("phone")}
                lineas = [{"codigo": (li.get("sku") or f"WOO-{li.get('product_id')}"),
                           "nombre": li.get("name"), "cantidad": _num(li.get("quantity"), 1),
                           "precio": _num(li.get("price"))} for li in (o.get("line_items") or [])]
                if not lineas:
                    continue
                try:
                    # MISMO motor de pedidos que TPV/Portal Web/Canal Web.
                    OS.crear_pedido_online(cliente, lineas, plataforma="woocommerce",
                                           referencia_externa=ref)
                    creados += 1
                except Exception as e:
                    logger.debug("crear pedido woo %s: %s", ref, e)
            if len(items) < por_pagina:
                break
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 6 · Exportación (solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.WOO_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            woo_id = it.get("woo_id") or self._woo_id_por_sku(sku, id_empresa)
            if not woo_id:
                continue
            try:
                stock = SA.stock_total_global(sku, id_empresa=id_empresa)
                self._req("PUT", f"products/{woo_id}", id_empresa,
                          json={"stock_quantity": int(stock), "manage_stock": True})
                n += 1
            except Exception as e:
                logger.debug("exportar stock %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.WOO_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            precio = it.get("precio")
            woo_id = it.get("woo_id") or self._woo_id_por_sku(sku, id_empresa)
            if not woo_id or precio is None:
                continue
            try:
                self._req("PUT", f"products/{woo_id}", id_empresa,
                          json={"regular_price": str(_num(precio))})
                n += 1
            except Exception as e:
                logger.debug("exportar precio %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    def _woo_id_por_sku(self, sku, id_empresa):
        if not sku:
            return None
        try:
            r = self._req("GET", "products", id_empresa, params={"sku": sku})
            return (r[0].get("id") if r else None)
        except Exception:
            return None

    # ── 7 · Estado de pedido (ERP → WooCommerce) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        estado_woo = _ESTADO_ERP_A_WOO.get(str(estado_erp).upper(), "processing")
        woo_id = str(id_externo).replace("WOO-", "")
        try:
            self._req("PUT", f"orders/{woo_id}", id_empresa, json={"status": estado_woo})
            return {"ok": True, "estado_woo": estado_woo}
        except IntegracionError as e:
            self._audit(A.WOO_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── Sincronización (reutiliza el pipeline/última sync del motor) ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.WOO_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "woocommerce", usuario=usuario)
            servicio.sincronizar(id_empresa, "woocommerce", usuario=usuario)   # estado + última sync
        except Exception as e:
            logger.debug("estado sync woo: %s", e)
        self._audit(A.WOO_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.WOO_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        # Usa la ÚLTIMA SINCRONIZACIÓN ya existente en el motor (no reimporta todo).
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "woocommerce") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "woocommerce", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc woo: %s", e)
        self._audit(A.WOO_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
