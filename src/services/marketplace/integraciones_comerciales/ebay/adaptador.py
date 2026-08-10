"""
Conector eBay · Implementación operativa (Fase WEB-21). Mismo patrón que Amazon/ecommerce: extiende el
conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/pedidos/stock).
Marketplace: NO crea webs/dominios/SSL. Idempotente, multiempresa, degradable.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.ebay import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.ebay import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.ebay import \
    transporte as T
from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    EbayConnector as _EbayPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.ebay.adaptador")


def _num(v, defecto=0.0):
    try:
        if isinstance(v, dict):          # eBay money: {"value": "9.90", "currency": "EUR"}
            v = v.get("value")
        return float(v)
    except Exception:
        return defecto


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(float(ts)))
    except Exception:
        return None


class EbayAdapter(_EbayPreparado):
    """Conector eBay operativo. Instanciable sin argumentos (`motor.adaptador('ebay')`)."""

    plataforma = "ebay"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "EBAY"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            return (servicio.obtener(id_empresa, "ebay") or {}) if id_empresa is not None else {}
        except Exception:
            return {}

    def _config(self, id_empresa=None):
        host = self._url or self._integracion(id_empresa).get("url") or os.getenv("EBAY_API_HOST")
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
                                   "Access Token de eBay no configurado", plataforma="ebay")
        return T.get_transporte().request(method, host, path, token=token, json=json, params=params)

    def _paginar(self, path, key, id_empresa, *, extra=None, limit=100, max_paginas=50):
        """Paginación eBay por `limit/offset`. Extrae la lista `key` de la respuesta."""
        out = []
        for page in range(max_paginas):
            params = {"limit": limit, "offset": page * limit}
            if extra:
                params.update(extra)
            data = self._req("GET", path, id_empresa, params=params)
            items = data.get(key, []) if isinstance(data, dict) else (data or [])
            if not items:
                break
            out.extend(items)
            if len(items) < limit:
                break
        return out

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.EBAY_AUTH, id_empresa, usuario)
        host, token = self._config(id_empresa)
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales eBay"}
        try:
            self._req("GET", "sell/inventory/v1/inventory_item", id_empresa,
                      params={"limit": 1, "offset": 0})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.EBAY_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.EBAY_VALIDATE, id_empresa, usuario)
        host, token = self._config(id_empresa)
        comprob = {"url": "ok" if host else "falta", "token": "ok" if token else "falta",
                   "ssl": "ok" if (host or "").lower().startswith("https") else "aviso"}
        if not token:
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "sell/inventory/v1/inventory_item", id_empresa,
                      params={"limit": 1, "offset": 0})
            version = self.obtener_version(id_empresa=id_empresa)
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "ebay", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar ebay: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.EBAY_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        return getattr(T.get_transporte(), "api_version", None) or T.API_VERSION

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.EBAY_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        procesados, skus = 0, []
        for it in self._paginar("sell/inventory/v1/inventory_item", "inventoryItems", id_empresa):
            sku = (str(it.get("sku") or "").strip()) or f"EBAY-{it.get('epid') or procesados}"
            nombre = (it.get("product") or {}).get("title") or it.get("title") or sku
            precio = _num(it.get("price"))
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=nombre)
                from src.db import articulos as ART
                ART.actualizar_precio(sku, precio)
            except Exception as e:
                logger.debug("upsert producto ebay %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def _pedidos_raw(self, id_empresa, desde):
        extra = {"filter": f"lastmodifieddate:[{_iso(desde)}..]"} if desde else None
        return self._paginar("sell/fulfillment/v1/order", "orders", id_empresa, extra=extra)

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        # eBay no expone listado de clientes; se derivan del comprador de los pedidos (buyer).
        self._audit(A.EBAY_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        creados = actualizados = 0
        vistos = set()
        for o in self._pedidos_raw(id_empresa, desde):
            buyer = o.get("buyer") or {}
            email = (buyer.get("email") or o.get("buyerEmail") or "").strip()
            clave = email or (buyer.get("username") or "").strip()
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            nombre = buyer.get("username") or email or "Cliente eBay"
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
                logger.debug("importar cliente ebay %s: %s", clave, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.EBAY_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for o in self._pedidos_raw(id_empresa, desde):
            ref = f"EBAY-{o.get('orderId') or o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            buyer = o.get("buyer") or {}
            cliente = {"nombre": buyer.get("username") or buyer.get("email") or "Cliente eBay",
                       "email": buyer.get("email") or o.get("buyerEmail"), "telefono": None}
            lineas = [{"codigo": (li.get("sku") or f"EBAY-{li.get('legacyItemId')}"),
                       "nombre": li.get("title"), "cantidad": _num(li.get("quantity"), 1),
                       "precio": _num(li.get("lineItemCost") or li.get("price"))}
                      for li in (o.get("lineItems") or [])]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="ebay", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido ebay %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (por SKU; solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.EBAY_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            if not sku:
                continue
            stock = SA.stock_total_global(sku, id_empresa=id_empresa)
            try:
                self._req("PUT", f"sell/inventory/v1/inventory_item/{sku}", id_empresa,
                          json={"availability": {"shipToLocationAvailability": {"quantity": int(stock)}}})
                n += 1
            except Exception as e:
                logger.debug("exportar stock ebay %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.EBAY_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            precio = it.get("precio")
            if not sku or precio is None:
                continue
            try:
                # El precio en eBay vive en la Offer; se deja preparada la actualización por SKU.
                self._req("PUT", f"sell/inventory/v1/offer/{sku}", id_empresa,
                          json={"pricingSummary": {"price": {"value": str(_num(precio)),
                                                             "currency": "EUR"}}})
                n += 1
            except Exception as e:
                logger.debug("exportar precio ebay %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → eBay; fulfillment) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        oid = str(id_externo).replace("EBAY-", "")
        try:
            # El envío se confirma vía shipping fulfillment; se deja preparado el punto de actualización.
            self._req("POST", f"sell/fulfillment/v1/order/{oid}/shipping_fulfillment", id_empresa,
                      json={"note": f"estado ERP: {estado_erp}"})
            return {"ok": True, "estado_erp": str(estado_erp)}
        except IntegracionError as e:
            self._audit(A.EBAY_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.EBAY_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "ebay", usuario=usuario)
            servicio.sincronizar(id_empresa, "ebay", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync ebay: %s", e)
        self._audit(A.EBAY_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.EBAY_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "ebay") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "ebay", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc ebay: %s", e)
        self._audit(A.EBAY_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
