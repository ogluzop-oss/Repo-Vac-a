"""
Conector Meta Shop (Instagram Shopping + Facebook Shop) · Implementación operativa. Cierra la
brecha confirmada por auditoría: NO existía ninguna integración de catálogo Instagram Shopping /
Facebook Shop en el repo (solo TikTok Shop) — mismo patrón que Amazon/eBay/Miravia/AliExpress/
TikTok Shop: extiende el conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP
(catálogo/clientes/pedidos/stock). Marketplace: NO crea webs/dominios/SSL. Idempotente,
multiempresa, degradable.

Instagram Shopping y Facebook Shop comparten el MISMO Catálogo de Comercio de Meta (un solo
`catalog_id`, gestionado desde Commerce Manager) — por eso TODA la lógica de sincronización vive
una sola vez en `_MetaShopBase`; las dos subclases (`InstagramShoppingAdapter`/
`FacebookShopAdapter`) solo fijan `plataforma` para que cada una aparezca como una conexión
independiente en el Centro de Integraciones (igual que en el propio Commerce Manager de Meta, que
trata cada canal como un interruptor independiente sobre el mismo catálogo).
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    InstagramShoppingConnector as _InstagramPreparado
from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    FacebookShopConnector as _FacebookPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.meta_shop import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.meta_shop import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.meta_shop import \
    transporte as T

logger = logging.getLogger("marketplace.integraciones_comerciales.meta_shop.adaptador")


def _num(v, defecto=0.0):
    try:
        return float(v)
    except Exception:
        return defecto


class _MetaShopBase:
    """Lógica real COMPARTIDA (ver docstring del módulo). No se instancia directamente — cada
    subclase añade su `plataforma` y hereda de su propio conector PREPARADO."""

    def __init__(self, *, credenciales_ref=None, url=None):
        self._credenciales_ref = credenciales_ref or "META_SHOP"
        self._url = url

    def _config(self, id_empresa=None):
        host = self._url or os.getenv("META_GRAPH_API_HOST")
        return (host or T.DEFAULT_HOST, S.access_token(self._credenciales_ref),
               S.catalog_id(self._credenciales_ref))

    def disponible(self, id_empresa=None) -> bool:
        host, token, catalog_id = self._config(id_empresa)
        return bool(host and token and catalog_id)

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["estado"] = "OPERATIVO" if self.disponible() else "PREPARADO"
        return d

    def _audit(self, evento, id_empresa=None, usuario=None, detalle=None):
        A.registrar(evento, id_empresa=id_empresa, usuario=usuario, detalle=detalle)

    def _req(self, method, path, id_empresa=None, *, json=None, params=None):
        host, token, catalog_id = self._config(id_empresa)
        if not token or not catalog_id:
            raise IntegracionError(CodigoError.MISSING_CREDENTIALS,
                                   "Access Token o Catalog ID de Meta Shop no configurados",
                                   plataforma=self.plataforma)
        return T.get_transporte().request(method, host, path, token=token, json=json, params=params)

    def _catalog_id(self, id_empresa=None):
        return self._config(id_empresa)[2]

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.META_SHOP_AUTH, id_empresa, usuario)
        _host, token, catalog_id = self._config(id_empresa)
        if not token or not catalog_id:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales Meta Shop"}
        try:
            self._req("GET", f"{catalog_id}", id_empresa, params={"fields": "id,name"})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.META_SHOP_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.META_SHOP_VALIDATE, id_empresa, usuario)
        host, token, catalog_id = self._config(id_empresa)
        comprob = {"catalog_id": "ok" if catalog_id else "falta", "token": "ok" if token else "falta",
                  "ssl": "ok" if (host or "").lower().startswith("https") else "aviso"}
        if not token or not catalog_id:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", f"{catalog_id}", id_empresa, params={"fields": "id,name,product_count"})
            comprob.update({"api": "ok", "permisos": "ok"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, self.plataforma, usuario=usuario)
            except Exception as e:
                logger.debug("estado validar meta_shop: %s", e)
            return {"ok": True, "estado": "VALIDADA", "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.META_SHOP_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        return getattr(T.get_transporte(), "api_version", None) or T.API_VERSION

    # ── 4 · Importación ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        """Meta Shop es, en la práctica totalidad de los casos reales, un catálogo que el ERP
        EXPORTA hacia Meta (el cliente no crea productos desde el lado de Meta) — igual criterio
        honesto que `importar_clientes` de TikTok Shop (deriva, no inventa un flujo inexistente).
        Se expone igualmente para listar lo que YA hay publicado en el catálogo (auditoría/
        comparación), sin tocar el ERP."""
        self._audit(A.META_SHOP_IMPORT, id_empresa, usuario, "productos (solo lectura)")
        catalog_id = self._catalog_id(id_empresa)
        productos, after = [], None
        for _ in range(50):
            params = {"fields": "id,retailer_id,name,price,availability,inventory", "limit": 100}
            if after:
                params["after"] = after
            data = self._req("GET", f"{catalog_id}/products", id_empresa, params=params)
            lote = data.get("data") or []
            productos.extend(lote)
            after = ((data.get("paging") or {}).get("cursors") or {}).get("after")
            if not after or not lote:
                break
        return {"ok": True, "procesados": len(productos), "productos": productos}

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        # Igual que en TikTok Shop: Meta Shop no expone un padrón de clientes propio; se derivarían
        # de los pedidos de Commerce Manager (ver `importar_pedidos`) si la cuenta los expone.
        self._audit(A.META_SHOP_IMPORT, id_empresa, usuario, "clientes")
        return {"ok": True, "creados": 0, "actualizados": 0,
               "aviso": "Meta Shop no expone un padrón de clientes propio; se derivan de los "
                        "pedidos de Commerce Manager."}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        """Commerce Manager Orders API — requiere una cuenta de comercio (`commerce_account_id`)
        con el permiso de gestión de pedidos. Degrada honestamente (MISSING_CREDENTIALS) si no
        está configurada; nunca inventa pedidos."""
        self._audit(A.META_SHOP_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.seguridad import secret_manager as sm
        commerce_account_id = sm.obtener_secreto(f"{self._credenciales_ref}_COMMERCE_ACCOUNT_ID")
        if not commerce_account_id:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "falta commerce_account_id (Meta Commerce Manager)"}
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        try:
            data = self._req("GET", f"{commerce_account_id}/orders", id_empresa,
                             params={"state": "CREATED", "limit": 100})
        except IntegracionError as e:
            self._audit(A.META_SHOP_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}
        for o in (data.get("data") or []):
            ref = f"{self.plataforma.upper()}-{o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                        for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            comprador = o.get("ship_address") or {}
            cliente = {"nombre": comprador.get("name") or "Cliente Meta Shop",
                      "email": o.get("buyer_details", {}).get("email"), "telefono": None}
            lineas = [{"codigo": it.get("retailer_id"), "nombre": it.get("product_name"),
                      "cantidad": _num(it.get("quantity"), 1), "precio": _num(it.get("price_per_unit"))}
                     for it in (o.get("items") or {}).get("data", [])]
            if not lineas:
                continue
            try:
                OS.crear_pedido_canal_externo(cliente, lineas, plataforma=self.plataforma,
                                              referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido meta_shop %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (ERP → Meta, vía Catalog Batch API, SKU=retailer_id) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.META_SHOP_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        catalog_id = self._catalog_id(id_empresa)
        requests_batch = []
        for it in (articulos or []):
            sku = it.get("sku")
            if not sku:
                continue
            stock = SA.stock_total_global(sku, id_empresa=id_empresa)
            requests_batch.append({"method": "UPDATE", "data": {
                "id": sku, "inventory": int(stock),
                "availability": "in stock" if stock > 0 else "out of stock"}})
        if not requests_batch:
            return {"ok": True, "exportados": 0}
        try:
            self._req("POST", f"{catalog_id}/batch", id_empresa,
                      json={"requests": requests_batch, "item_type": "PRODUCT_ITEM"})
        except IntegracionError as e:
            self._audit(A.META_SHOP_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}
        return {"ok": True, "exportados": len(requests_batch)}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.META_SHOP_EXPORT, id_empresa, usuario, "precios")
        catalog_id = self._catalog_id(id_empresa)
        requests_batch = [{"method": "UPDATE", "data": {
                            "id": it["sku"], "price": f"{_num(it.get('precio')):.2f} EUR"}}
                          for it in (articulos or []) if it.get("sku") and it.get("precio") is not None]
        if not requests_batch:
            return {"ok": True, "exportados": 0}
        try:
            self._req("POST", f"{catalog_id}/batch", id_empresa,
                      json={"requests": requests_batch, "item_type": "PRODUCT_ITEM"})
        except IntegracionError as e:
            self._audit(A.META_SHOP_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}
        return {"ok": True, "exportados": len(requests_batch)}

    # ── 7 · Estado de pedido (ERP → Meta) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        from src.services.seguridad import secret_manager as sm
        commerce_account_id = sm.obtener_secreto(f"{self._credenciales_ref}_COMMERCE_ACCOUNT_ID")
        if not commerce_account_id:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        oid = str(id_externo).replace(f"{self.plataforma.upper()}-", "")
        try:
            self._req("POST", f"{oid}/acknowledge_order" if estado_erp == "confirmado" else
                     f"{oid}/cancellations", id_empresa, json={})
            return {"ok": True, "estado_erp": str(estado_erp)}
        except IntegracionError as e:
            self._audit(A.META_SHOP_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.META_SHOP_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        from src.db import catalogo as CAT
        productos = CAT.listar_productos(solo_visibles=True, id_empresa=id_empresa, limite=5000)
        articulos = [{"sku": p.get("codigo_articulo"), "precio": p.get("precio")}
                    for p in productos if p.get("codigo_articulo")]
        res = {"stock": self.exportar_stock(id_empresa=id_empresa, usuario=usuario, articulos=articulos),
               "precios": self.exportar_precios(id_empresa=id_empresa, usuario=usuario, articulos=articulos),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, self.plataforma, usuario=usuario)
            servicio.sincronizar(id_empresa, self.plataforma, usuario=usuario)
        except Exception as e:
            logger.debug("estado sync meta_shop: %s", e)
        self._audit(A.META_SHOP_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        return self.sincronizacion_inicial(id_empresa=id_empresa, usuario=usuario)


class InstagramShoppingAdapter(_MetaShopBase, _InstagramPreparado):
    """Instantiable sin argumentos (`motor.adaptador('instagram_shopping')`)."""
    plataforma = "instagram_shopping"

    def __init__(self, *, credenciales_ref=None, url=None):
        _InstagramPreparado.__init__(self)
        _MetaShopBase.__init__(self, credenciales_ref=credenciales_ref, url=url)


class FacebookShopAdapter(_MetaShopBase, _FacebookPreparado):
    """Instantiable sin argumentos (`motor.adaptador('facebook_shop')`)."""
    plataforma = "facebook_shop"

    def __init__(self, *, credenciales_ref=None, url=None):
        _FacebookPreparado.__init__(self)
        _MetaShopBase.__init__(self, credenciales_ref=credenciales_ref, url=url)
