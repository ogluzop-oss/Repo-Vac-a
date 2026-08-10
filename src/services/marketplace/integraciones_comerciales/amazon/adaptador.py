"""
Conector Amazon · Implementación operativa (Fase WEB-20). Mismo patrón que los ecommerce: extiende el conector
PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/pedidos/stock). Marketplace: NO
crea webs/dominios/SSL. Idempotente, multiempresa, degradable.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.amazon import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.amazon import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.amazon import \
    transporte as T
from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    AmazonConnector as _AmazonPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.amazon.adaptador")


def _num(v, defecto=0.0):
    try:
        if isinstance(v, dict):          # SP-API money: {"Amount": "9.90", "CurrencyCode": "EUR"}
            v = v.get("Amount")
        return float(v)
    except Exception:
        return defecto


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


class AmazonAdapter(_AmazonPreparado):
    """Conector Amazon operativo. Instanciable sin argumentos (`motor.adaptador('amazon')`)."""

    plataforma = "amazon"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "AMAZON"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            return (servicio.obtener(id_empresa, "amazon") or {}) if id_empresa is not None else {}
        except Exception:
            return {}

    def _config(self, id_empresa=None):
        host = self._url or self._integracion(id_empresa).get("url") or os.getenv("AMAZON_SPAPI_HOST")
        return host or T.DEFAULT_HOST, S.access_token(self._credenciales_ref)

    def _marketplace_id(self, id_empresa=None):
        return os.getenv("AMAZON_MARKETPLACE_ID", "A1RKKUPIHCS9HS")   # ES por defecto

    def disponible(self, id_empresa=None) -> bool:
        host, token = self._config(id_empresa)
        # El host tiene un valor por defecto; lo que determina disponibilidad es el Access Token real.
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
                                   "Access Token de Amazon SP-API no configurado", plataforma="amazon")
        return T.get_transporte().request(method, host, path, token=token, json=json, params=params)

    @staticmethod
    def _payload(data):
        return data.get("payload", data) if isinstance(data, dict) else data

    def _sp_list(self, path, key, id_empresa, *, params=None, max_paginas=50):
        """Recorre una lista SP-API paginada por `NextToken`. Extrae `key` del payload."""
        out, token = [], None
        for _ in range(max_paginas):
            p = dict(params or {})
            if token:
                p["NextToken"] = token
            pay = self._payload(self._req("GET", path, id_empresa, params=p))
            items = pay.get(key, []) if isinstance(pay, dict) else (pay or [])
            out.extend(items)
            token = pay.get("NextToken") if isinstance(pay, dict) else None
            if not token:
                break
        return out

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.AMAZON_AUTH, id_empresa, usuario)
        host, token = self._config(id_empresa)
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales Amazon"}
        try:
            self._req("GET", "orders/v0/orders", id_empresa,
                      params={"MarketplaceIds": self._marketplace_id(id_empresa),
                              "CreatedAfter": _iso(time.time() - 86400)})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.AMAZON_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.AMAZON_VALIDATE, id_empresa, usuario)
        host, token = self._config(id_empresa)
        comprob = {"url": "ok" if host else "falta", "token": "ok" if token else "falta",
                   "ssl": "ok" if (host or "").lower().startswith("https") else "aviso"}
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "orders/v0/orders", id_empresa,
                      params={"MarketplaceIds": self._marketplace_id(id_empresa),
                              "CreatedAfter": _iso(time.time() - 86400)})
            version = self.obtener_version(id_empresa=id_empresa)
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "amazon", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar amazon: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.AMAZON_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        return getattr(T.get_transporte(), "api_version", None) or T.API_VERSION

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.AMAZON_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        params = {"marketplaceIds": self._marketplace_id(id_empresa)}
        procesados, skus = 0, []
        for it in self._sp_list("listings/2021-08-01/items", "items", id_empresa, params=params):
            sums = it.get("summaries") or [{}]
            sku = (str(it.get("sku") or it.get("sellerSku") or "").strip()) or f"AMAZON-{it.get('asin')}"
            nombre = it.get("name") or sums[0].get("itemName") or sku
            precio = _num(it.get("price"))
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=nombre)
                from src.db import articulos as ART
                ART.actualizar_precio(sku, precio)
            except Exception as e:
                logger.debug("upsert producto amazon %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        # Amazon no expone un listado de clientes; se derivan del comprador de los pedidos (BuyerInfo).
        self._audit(A.AMAZON_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        creados = actualizados = 0
        vistos = set()
        for o in self._pedidos_raw(id_empresa, desde):
            bi = o.get("BuyerInfo") or {}
            email = (bi.get("BuyerEmail") or "").strip()
            if not email or email in vistos:
                continue
            vistos.add(email)
            nombre = bi.get("BuyerName") or email
            try:
                existente = None
                for r in (CL.buscar_clientes(email) or []):
                    if str(r.get("email", "")).lower() == email.lower():
                        existente = r
                        break
                if existente:
                    CL.actualizar_cliente(existente.get("id"))
                    actualizados += 1
                else:
                    CL.crear_cliente(nombre, email=email)
                    creados += 1
            except Exception as e:
                logger.debug("importar cliente amazon %s: %s", email, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def _pedidos_raw(self, id_empresa, desde):
        params = {"MarketplaceIds": self._marketplace_id(id_empresa)}
        if desde:
            params["LastUpdatedAfter"] = _iso(desde)
        else:
            params["CreatedAfter"] = _iso(time.time() - 30 * 86400)
        return self._sp_list("orders/v0/orders", "Orders", id_empresa, params=params)

    def _order_items(self, amazon_order_id, id_empresa):
        pay = self._payload(self._req("GET", f"orders/v0/orders/{amazon_order_id}/orderItems", id_empresa))
        return pay.get("OrderItems", []) if isinstance(pay, dict) else (pay or [])

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.AMAZON_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for o in self._pedidos_raw(id_empresa, desde):
            aoid = o.get("AmazonOrderId") or o.get("id")
            ref = f"AMAZON-{aoid}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            bi = o.get("BuyerInfo") or {}
            cliente = {"nombre": bi.get("BuyerName") or bi.get("BuyerEmail") or "Cliente Amazon",
                       "email": bi.get("BuyerEmail"), "telefono": None}
            lineas = [{"codigo": (li.get("SellerSKU") or f"AMAZON-{li.get('ASIN')}"),
                       "nombre": li.get("Title"), "cantidad": _num(li.get("QuantityOrdered"), 1),
                       "precio": _num(li.get("ItemPrice"))} for li in self._order_items(aoid, id_empresa)]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="amazon", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido amazon %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (por SKU; solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.AMAZON_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            if not sku:
                continue
            stock = SA.stock_total_global(sku, id_empresa=id_empresa)
            try:
                self._req("PUT", f"listings/2021-08-01/items/{sku}", id_empresa,
                          json={"productType": "PRODUCT", "patches": [
                              {"op": "replace", "path": "/attributes/fulfillment_availability",
                               "value": [{"quantity": int(stock)}]}]})
                n += 1
            except Exception as e:
                logger.debug("exportar stock amazon %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.AMAZON_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            precio = it.get("precio")
            if not sku or precio is None:
                continue
            try:
                self._req("PUT", f"listings/2021-08-01/items/{sku}", id_empresa,
                          json={"productType": "PRODUCT", "patches": [
                              {"op": "replace", "path": "/attributes/purchasable_offer",
                               "value": [{"our_price": [{"schedule": [{"value_with_tax": _num(precio)}]}]}]}]})
                n += 1
            except Exception as e:
                logger.debug("exportar precio amazon %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → Amazon; gestionado por Amazon/feeds) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        # El estado/fulfillment de pedidos Amazon se gestiona vía Feeds (asíncrono). Se deja preparado.
        return {"ok": False, "motivo": "estado gestionado por Amazon (Feeds); preparado, no ejecutado",
                "estado_erp": str(estado_erp)}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.AMAZON_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "amazon", usuario=usuario)
            servicio.sincronizar(id_empresa, "amazon", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync amazon: %s", e)
        self._audit(A.AMAZON_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.AMAZON_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "amazon") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "amazon", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc amazon: %s", e)
        self._audit(A.AMAZON_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
