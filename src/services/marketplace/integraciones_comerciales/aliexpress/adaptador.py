"""
Conector AliExpress · Implementación operativa (Fase WEB-23). Mismo patrón que Amazon/eBay/Miravia/ecommerce:
extiende el conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/pedidos/
stock). Marketplace: NO crea webs/dominios/SSL. Idempotente, multiempresa, degradable.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.aliexpress import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.aliexpress import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.aliexpress import \
    transporte as T
from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    AliExpressConnector as _AliExpressPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.aliexpress.adaptador")


def _num(v, defecto=0.0):
    try:
        if isinstance(v, dict):
            v = v.get("value") or v.get("amount")
        return float(v)
    except Exception:
        return defecto


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(float(ts)))
    except Exception:
        return None


class AliExpressAdapter(_AliExpressPreparado):
    """Conector AliExpress operativo. Instanciable sin argumentos (`motor.adaptador('aliexpress')`)."""

    plataforma = "aliexpress"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "ALIEXPRESS"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            return (servicio.obtener(id_empresa, "aliexpress") or {}) if id_empresa is not None else {}
        except Exception:
            return {}

    def _config(self, id_empresa=None):
        host = self._url or self._integracion(id_empresa).get("url") or os.getenv("ALIEXPRESS_API_HOST")
        return host or T.DEFAULT_HOST, S.access_token(self._credenciales_ref)

    def disponible(self, id_empresa=None) -> bool:
        host, token = self._config(id_empresa)
        return bool(host and token)

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["estado"] = "OPERATIVO" if self.disponible() else "PREPARADO"
        return d

    def _audit(self, evento, id_empresa=None, usuario=None, detalle=None):
        A.registrar(evento, id_empresa=id_empresa, usuario=usuario, detalle=detalle)

    def _req(self, method, path, id_empresa=None, *, json=None, params=None):
        host, token = self._config(id_empresa)
        if not token:
            raise IntegracionError(CodigoError.MISSING_CREDENTIALS,
                                   "Access Token de AliExpress no configurado", plataforma="aliexpress")
        return T.get_transporte().request(method, host, path, token=token, json=json, params=params)

    @staticmethod
    def _lista(data, key):
        """La Open Platform envuelve en {key:[...]}, {'data':{key:[...]}} o {'result':{key:[...]}}."""
        if isinstance(data, dict):
            if isinstance(data.get(key), list):
                return data[key]
            for envoltura in ("data", "result"):
                sub = data.get(envoltura)
                if isinstance(sub, dict) and isinstance(sub.get(key), list):
                    return sub[key]
            return []
        return data or []

    def _incremental(self, desde):
        return {"update_after": _iso(desde)} if desde else None

    def _paginar(self, path, key, id_empresa, *, extra=None, limit=100, max_paginas=50):
        out = []
        for page in range(max_paginas):
            params = {"limit": limit, "offset": page * limit}
            if extra:
                params.update(extra)
            items = self._lista(self._req("GET", path, id_empresa, params=params), key)
            if not items:
                break
            out.extend(items)
            if len(items) < limit:
                break
        return out

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.ALIEXPRESS_AUTH, id_empresa, usuario)
        host, token = self._config(id_empresa)
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales AliExpress"}
        try:
            self._req("GET", "products", id_empresa, params={"limit": 1, "offset": 0})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.ALIEXPRESS_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.ALIEXPRESS_VALIDATE, id_empresa, usuario)
        host, token = self._config(id_empresa)
        comprob = {"url": "ok" if host else "falta", "token": "ok" if token else "falta",
                   "ssl": "ok" if (host or "").lower().startswith("https") else "aviso"}
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "products", id_empresa, params={"limit": 1, "offset": 0})
            version = self.obtener_version(id_empresa=id_empresa)
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "aliexpress", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar aliexpress: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.ALIEXPRESS_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        return getattr(T.get_transporte(), "api_version", None) or T.API_VERSION

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.ALIEXPRESS_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        procesados, skus = 0, []
        for p in self._paginar("products", "products", id_empresa, extra=self._incremental(desde)):
            sku = (str(p.get("sku") or p.get("seller_sku") or "").strip()) \
                or f"ALIEXPRESS-{p.get('product_id') or p.get('id')}"
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=p.get("name") or p.get("subject"))
                from src.db import articulos as ART
                ART.actualizar_precio(sku, _num(p.get("price")))
            except Exception as e:
                logger.debug("upsert producto aliexpress %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def _pedidos_raw(self, id_empresa, desde):
        return self._paginar("orders", "orders", id_empresa, extra=self._incremental(desde))

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        # AliExpress solo expone clientes asociados a pedidos: se derivan del comprador de los pedidos.
        self._audit(A.ALIEXPRESS_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        creados = actualizados = 0
        vistos = set()
        for o in self._pedidos_raw(id_empresa, desde):
            buyer = o.get("buyer") or o.get("customer") or {}
            email = (buyer.get("email") or o.get("buyer_email") or "").strip()
            clave = email or (buyer.get("name") or "").strip()
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            nombre = buyer.get("name") or email or "Cliente AliExpress"
            try:
                existente = None
                if email:
                    for r in (CL.buscar_clientes(email) or []):
                        if str(r.get("email", "")).lower() == email.lower():
                            existente = r
                            break
                if existente:
                    CL.actualizar_cliente(existente.get("id"))
                    actualizados += 1
                else:
                    CL.crear_cliente(nombre, email=email or None)
                    creados += 1
            except Exception as e:
                logger.debug("importar cliente aliexpress %s: %s", clave, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.ALIEXPRESS_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for o in self._pedidos_raw(id_empresa, desde):
            ref = f"ALIEXPRESS-{o.get('order_id') or o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            buyer = o.get("buyer") or o.get("customer") or {}
            cliente = {"nombre": buyer.get("name") or buyer.get("email") or "Cliente AliExpress",
                       "email": buyer.get("email") or o.get("buyer_email"), "telefono": None}
            filas = o.get("items") or o.get("order_lines") or []
            lineas = [{"codigo": (li.get("sku") or f"ALIEXPRESS-{li.get('product_id')}"),
                       "nombre": li.get("name") or li.get("subject"), "cantidad": _num(li.get("quantity"), 1),
                       "precio": _num(li.get("price"))} for li in filas]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="aliexpress", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido aliexpress %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (por SKU/id; solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.ALIEXPRESS_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            ident = it.get("aliexpress_id") or it.get("product_id") or it.get("sku")
            if not ident:
                continue
            stock = SA.stock_total_global(it.get("sku"), id_empresa=id_empresa) if it.get("sku") else 0
            try:
                self._req("PUT", f"products/{ident}", id_empresa, json={"quantity": int(stock)})
                n += 1
            except Exception as e:
                logger.debug("exportar stock aliexpress %s: %s", ident, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.ALIEXPRESS_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            ident = it.get("aliexpress_id") or it.get("product_id") or it.get("sku")
            precio = it.get("precio")
            if not ident or precio is None:
                continue
            try:
                self._req("PUT", f"products/{ident}", id_empresa, json={"price": _num(precio)})
                n += 1
            except Exception as e:
                logger.debug("exportar precio aliexpress %s: %s", ident, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → AliExpress) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        oid = str(id_externo).replace("ALIEXPRESS-", "")
        try:
            self._req("PUT", f"orders/{oid}", id_empresa, json={"status": str(estado_erp)})
            return {"ok": True, "estado_erp": str(estado_erp)}
        except IntegracionError as e:
            self._audit(A.ALIEXPRESS_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.ALIEXPRESS_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "aliexpress", usuario=usuario)
            servicio.sincronizar(id_empresa, "aliexpress", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync aliexpress: %s", e)
        self._audit(A.ALIEXPRESS_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.ALIEXPRESS_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "aliexpress") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "aliexpress", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc aliexpress: %s", e)
        self._audit(A.ALIEXPRESS_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
