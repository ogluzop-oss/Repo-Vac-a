"""
Conector Magento · Implementación operativa (Fase WEB-18). Mismo patrón que WooCommerce/Shopify/PrestaShop:
extiende el conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/pedidos/
stock). Toda la lógica específica de Magento vive aquí. Idempotente, multiempresa, degradable.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.magento import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.magento import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.magento import \
    transporte as T
from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    MagentoConnector as _MagentoPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.magento.adaptador")


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


class MagentoAdapter(_MagentoPreparado):
    """Conector Magento operativo. Instanciable sin argumentos (`motor.adaptador('magento')`)."""

    plataforma = "magento"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "MAGENTO"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _url_integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "magento") if id_empresa is not None else None
            return i.get("url") if i else None
        except Exception:
            return None

    def _config(self, id_empresa=None):
        url = self._url or self._url_integracion(id_empresa) or os.getenv("MAGENTO_URL")
        return url, S.access_token(self._credenciales_ref)

    def disponible(self, id_empresa=None) -> bool:
        url, token = self._config(id_empresa)
        return bool(url and token)

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["estado"] = "OPERATIVO" if self.disponible() else "PREPARADO"
        return d

    def _audit(self, evento, id_empresa=None, usuario=None, detalle=None):
        A.registrar(evento, id_empresa=id_empresa, usuario=usuario, detalle=detalle)

    def _req(self, method, path, id_empresa=None, *, json=None, params=None):
        url, token = self._config(id_empresa)
        if not (url and token):
            raise IntegracionError(CodigoError.MISSING_CREDENTIALS,
                                   "Shop URL/Access Token de Magento no configurados", plataforma="magento")
        return T.get_transporte().request(method, url, path, token=token, json=json, params=params)

    def _paginar(self, recurso, id_empresa, *, extra=None, page_size=100, max_paginas=50):
        """Paginación Magento por `searchCriteria[pageSize]/[currentPage]`. Extrae `items`."""
        out = []
        for page in range(1, max_paginas + 1):
            params = {"searchCriteria[pageSize]": page_size, "searchCriteria[currentPage]": page}
            if extra:
                params.update(extra)
            data = self._req("GET", recurso, id_empresa, params=params)
            items = data.get("items", []) if isinstance(data, dict) else (data or [])
            if not items:
                break
            out.extend(items)
            if len(items) < page_size:
                break
        return out

    def _incremental(self, desde):
        if not desde:
            return None
        return {
            "searchCriteria[filterGroups][0][filters][0][field]": "updated_at",
            "searchCriteria[filterGroups][0][filters][0][value]": _iso(desde),
            "searchCriteria[filterGroups][0][filters][0][conditionType]": "gteq",
        }

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.MAGENTO_AUTH, id_empresa, usuario)
        url, token = self._config(id_empresa)
        if not (url and token):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales Magento"}
        try:
            self._req("GET", "products", id_empresa,
                      params={"searchCriteria[pageSize]": 1, "searchCriteria[currentPage]": 1})
            return {"ok": True}
        except IntegracionError as e:
            self._audit(A.MAGENTO_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.MAGENTO_VALIDATE, id_empresa, usuario)
        url, token = self._config(id_empresa)
        comprob = {"url": "ok" if url else "falta", "token": "ok" if token else "falta",
                   "ssl": "ok" if (url or "").lower().startswith("https") else "aviso"}
        if not (url and token):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "products", id_empresa,
                      params={"searchCriteria[pageSize]": 1, "searchCriteria[currentPage]": 1})
            version = self.obtener_version(id_empresa=id_empresa)
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "magento", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar magento: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version, "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.MAGENTO_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        return getattr(T.get_transporte(), "api_version", None) or T.API_VERSION

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.MAGENTO_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        procesados, skus = 0, []
        for p in self._paginar("products", id_empresa, extra=self._incremental(desde)):
            sku = (str(p.get("sku") or "").strip()) or f"MAGENTO-{p.get('id')}"
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=p.get("name"))
                from src.db import articulos as ART
                ART.actualizar_precio(sku, _num(p.get("price")))
            except Exception as e:
                logger.debug("upsert producto magento %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.MAGENTO_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        creados = actualizados = 0
        for c in self._paginar("customers/search", id_empresa, extra=self._incremental(desde)):
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
                    CL.actualizar_cliente(existente.get("id"))
                    actualizados += 1
                else:
                    CL.crear_cliente(nombre, email=email or None)
                    creados += 1
            except Exception as e:
                logger.debug("importar cliente magento %s: %s", email, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.MAGENTO_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for o in self._paginar("orders", id_empresa, extra=self._incremental(desde)):
            ref = f"MAGENTO-{o.get('entity_id') or o.get('increment_id') or o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            cliente = {"nombre": " ".join(x for x in (o.get("customer_firstname"),
                                                      o.get("customer_lastname")) if x)
                       or (o.get("customer_email") or "Cliente Web"),
                       "email": o.get("customer_email"), "telefono": None}
            lineas = [{"codigo": (li.get("sku") or f"MAGENTO-{li.get('product_id')}"),
                       "nombre": li.get("name"), "cantidad": _num(li.get("qty_ordered"), 1),
                       "precio": _num(li.get("price"))} for li in (o.get("items") or [])]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="magento", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido magento %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (por SKU; solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.MAGENTO_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            if not sku:
                continue
            stock = SA.stock_total_global(sku, id_empresa=id_empresa)
            try:
                self._req("PUT", f"products/{sku}", id_empresa,
                          json={"product": {"sku": sku, "extension_attributes": {
                              "stock_item": {"qty": int(stock), "is_in_stock": int(stock) > 0}}}})
                n += 1
            except Exception as e:
                logger.debug("exportar stock magento %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.MAGENTO_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            sku = it.get("sku")
            precio = it.get("precio")
            if not sku or precio is None:
                continue
            try:
                self._req("PUT", f"products/{sku}", id_empresa,
                          json={"product": {"sku": sku, "price": _num(precio)}})
                n += 1
            except Exception as e:
                logger.debug("exportar precio magento %s: %s", sku, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → Magento) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        oid = str(id_externo).replace("MAGENTO-", "")
        try:
            self._req("POST", f"orders/{oid}/comments", id_empresa,
                      json={"statusHistory": {"comment": f"estado ERP: {estado_erp}"}})
            return {"ok": True, "estado_erp": str(estado_erp)}
        except IntegracionError as e:
            self._audit(A.MAGENTO_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.MAGENTO_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "magento", usuario=usuario)
            servicio.sincronizar(id_empresa, "magento", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync magento: %s", e)
        self._audit(A.MAGENTO_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.MAGENTO_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "magento") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "magento", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc magento: %s", e)
        self._audit(A.MAGENTO_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
