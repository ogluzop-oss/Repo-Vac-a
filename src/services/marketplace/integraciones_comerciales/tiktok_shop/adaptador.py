"""
Conector TikTok Shop · Implementación operativa (Fase WEB-24). Mismo patrón que Amazon/eBay/Miravia/AliExpress
/ecommerce: extiende el conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/
pedidos/stock). Marketplace: NO crea webs/dominios/SSL. Idempotente, multiempresa, degradable.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    TikTokShopConnector as _TikTokPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.tiktok_shop import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.tiktok_shop import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.tiktok_shop import \
    transporte as T

logger = logging.getLogger("marketplace.integraciones_comerciales.tiktok_shop.adaptador")


def _num(v, defecto=0.0):
    try:
        if isinstance(v, dict):
            v = v.get("value") or v.get("amount") or v.get("sale_price")
        return float(v)
    except Exception:
        return defecto


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(float(ts)))
    except Exception:
        return None


class TikTokShopAdapter(_TikTokPreparado):
    """Conector TikTok Shop operativo. Instanciable sin argumentos (`motor.adaptador('tiktok_shop')`)."""

    plataforma = "tiktok_shop"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "TIKTOK"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            return (servicio.obtener(id_empresa, "tiktok_shop") or {}) if id_empresa is not None else {}
        except Exception:
            return {}

    def _config(self, id_empresa=None):
        host = self._url or self._integracion(id_empresa).get("url") or os.getenv("TIKTOK_API_HOST")
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
                                   "Access Token de TikTok Shop no configurado", plataforma="tiktok_shop")
        return T.get_transporte().request(method, host, path, token=token, json=json, params=params)

    @staticmethod
    def _lista(data, key):
        """La Partner API envuelve en {key:[...]} o {'data':{key:[...]}} (code/message envuelven data)."""
        if isinstance(data, dict):
            if isinstance(data.get(key), list):
                return data[key]
            sub = data.get("data")
            if isinstance(sub, dict) and isinstance(sub.get(key), list):
                return sub[key]
            return []
        return data or []

    def _incremental(self, desde):
        return {"update_time_ge": int(desde)} if desde else None

    def _paginar(self, path, key, id_empresa, *, extra=None, limit=100, max_paginas=50):
        out = []
        for page in range(max_paginas):
            params = {"page_size": limit, "page_number": page + 1, "offset": page * limit}
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
        self._audit(A.TIKTOK_AUTH, id_empresa, usuario)
        host, token = self._config(id_empresa)
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales TikTok Shop"}
        try:
            self._req("GET", "product/202309/products/search", id_empresa,
                      params={"page_size": 1, "page_number": 1})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.TIKTOK_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.TIKTOK_VALIDATE, id_empresa, usuario)
        host, token = self._config(id_empresa)
        comprob = {"url": "ok" if host else "falta", "token": "ok" if token else "falta",
                   "ssl": "ok" if (host or "").lower().startswith("https") else "aviso"}
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "product/202309/products/search", id_empresa,
                      params={"page_size": 1, "page_number": 1})
            version = self.obtener_version(id_empresa=id_empresa)
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "tiktok_shop", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar tiktok: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.TIKTOK_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        return getattr(T.get_transporte(), "api_version", None) or T.API_VERSION

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.TIKTOK_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        procesados, skus = 0, []
        for p in self._paginar("product/202309/products/search", "products", id_empresa,
                               extra=self._incremental(desde)):
            skus_p = p.get("skus") or []
            sku = (str((skus_p[0].get("seller_sku") if skus_p else None) or p.get("sku") or "").strip()) \
                or f"TIKTOK-{p.get('id') or p.get('product_id')}"
            precio = _num((skus_p[0].get("price") if skus_p else None) or p.get("price"))
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=p.get("title") or p.get("name"))
                from src.db import articulos as ART
                ART.actualizar_precio(sku, precio)
            except Exception as e:
                logger.debug("upsert producto tiktok %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def _pedidos_raw(self, id_empresa, desde):
        return self._paginar("order/202309/orders/search", "orders", id_empresa,
                             extra=self._incremental(desde))

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        # TikTok Shop solo expone clientes asociados a pedidos: se derivan del comprador de los pedidos.
        self._audit(A.TIKTOK_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        creados = actualizados = 0
        vistos = set()
        for o in self._pedidos_raw(id_empresa, desde):
            buyer = o.get("buyer") or o.get("recipient_address") or {}
            email = (buyer.get("email") or o.get("buyer_email") or "").strip()
            clave = email or (buyer.get("name") or buyer.get("username") or "").strip()
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            nombre = buyer.get("name") or buyer.get("username") or email or "Cliente TikTok"
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
                logger.debug("importar cliente tiktok %s: %s", clave, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.TIKTOK_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for o in self._pedidos_raw(id_empresa, desde):
            ref = f"TIKTOK-{o.get('id') or o.get('order_id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            buyer = o.get("buyer") or o.get("recipient_address") or {}
            cliente = {"nombre": buyer.get("name") or buyer.get("username") or "Cliente TikTok",
                       "email": buyer.get("email") or o.get("buyer_email"), "telefono": None}
            filas = o.get("line_items") or o.get("items") or []
            lineas = [{"codigo": (li.get("seller_sku") or li.get("sku") or f"TIKTOK-{li.get('product_id')}"),
                       "nombre": li.get("product_name") or li.get("name"),
                       "cantidad": _num(li.get("quantity"), 1),
                       "precio": _num(li.get("sale_price") or li.get("price"))} for li in filas]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="tiktok_shop", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido tiktok %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (por SKU/id; solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.TIKTOK_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            ident = it.get("tiktok_id") or it.get("product_id") or it.get("sku")
            if not ident:
                continue
            stock = SA.stock_total_global(it.get("sku"), id_empresa=id_empresa) if it.get("sku") else 0
            try:
                self._req("PUT", f"product/202309/products/{ident}/inventory/update", id_empresa,
                          json={"quantity": int(stock)})
                n += 1
            except Exception as e:
                logger.debug("exportar stock tiktok %s: %s", ident, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.TIKTOK_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            ident = it.get("tiktok_id") or it.get("product_id") or it.get("sku")
            precio = it.get("precio")
            if not ident or precio is None:
                continue
            try:
                self._req("PUT", f"product/202309/products/{ident}/prices/update", id_empresa,
                          json={"price": _num(precio)})
                n += 1
            except Exception as e:
                logger.debug("exportar precio tiktok %s: %s", ident, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → TikTok Shop) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        oid = str(id_externo).replace("TIKTOK-", "")
        try:
            self._req("POST", f"order/202309/orders/{oid}/status", id_empresa,
                      json={"status": str(estado_erp)})
            return {"ok": True, "estado_erp": str(estado_erp)}
        except IntegracionError as e:
            self._audit(A.TIKTOK_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.TIKTOK_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "tiktok_shop", usuario=usuario)
            servicio.sincronizar(id_empresa, "tiktok_shop", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync tiktok: %s", e)
        self._audit(A.TIKTOK_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.TIKTOK_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "tiktok_shop") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "tiktok_shop", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc tiktok: %s", e)
        self._audit(A.TIKTOK_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
