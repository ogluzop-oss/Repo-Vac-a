"""
Conector Shopify · Implementación operativa (Fase WEB-16). Mismo patrón que WooCommerce (WEB-15): extiende el
conector PREPARADO del motor WEB-13 y reutiliza los MOTORES del ERP (catálogo/clientes/pedidos/stock). Toda la
lógica específica de Shopify vive aquí. Idempotente, multiempresa, degradable. Plantilla reutilizable para
PrestaShop/Magento/OpenCart/Amazon/eBay/Miravia/AliExpress/TikTok.
"""

import logging
import os
import time

from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    ShopifyConnector as _ShopifyPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.shopify import \
    auditoria as A
from src.services.marketplace.integraciones_comerciales.shopify import \
    secretos as S
from src.services.marketplace.integraciones_comerciales.shopify import \
    transporte as T

logger = logging.getLogger("marketplace.integraciones_comerciales.shopify.adaptador")

# Estado ERP → estado/acción Shopify (referencia; la transición real se prepara con las costuras del motor).
_ESTADO_ERP_A_SHOPIFY = {"PENDIENTE": "open", "PAGADO": "open", "PREPARANDO": "open",
                         "ENVIADO": "fulfilled", "ENTREGADO": "fulfilled", "CANCELADO": "cancelled"}


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


def _sku_de_producto(p):
    variantes = p.get("variants") or []
    if variantes and (variantes[0].get("sku") or "").strip():
        return variantes[0]["sku"].strip()
    return f"SHOPIFY-{p.get('id')}"


class ShopifyAdapter(_ShopifyPreparado):
    """Conector Shopify operativo. Instanciable sin argumentos (`motor.adaptador('shopify')`)."""

    plataforma = "shopify"

    def __init__(self, *, credenciales_ref=None, url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or "SHOPIFY"
        self._url = url

    # ── Configuración / disponibilidad ──
    def _url_integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "shopify") if id_empresa is not None else None
            return i.get("url") if i else None
        except Exception:
            return None

    def _config(self, id_empresa=None):
        url = self._url or self._url_integracion(id_empresa) or os.getenv("SHOPIFY_URL")
        token = S.access_token(self._credenciales_ref)
        return url, token

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
                                   "Shop URL/Access Token de Shopify no configurados", plataforma="shopify")
        return T.get_transporte().request(method, url, path, token=token, json=json, params=params)

    def _paginar(self, recurso, id_empresa, *, extra=None, limite=250, max_paginas=50):
        """Paginación Shopify por `since_id` (genérico). Extrae la lista `recurso` de la respuesta."""
        since, out = 0, []
        for _ in range(max_paginas):
            params = {"limit": limite, "since_id": since}
            if extra:
                params.update(extra)
            data = self._req("GET", f"{recurso}.json", id_empresa, params=params)
            items = data.get(recurso, []) if isinstance(data, dict) else (data or [])
            if not items:
                break
            out.extend(items)
            try:
                since = max(int(i.get("id", 0)) for i in items)
            except Exception:
                since += len(items)
            if len(items) < limite:
                break
        return out

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.SHOPIFY_AUTH, id_empresa, usuario)
        url, token = self._config(id_empresa)
        if not (url and token):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales Shopify"}
        try:
            r = self._req("GET", "shop.json", id_empresa)
            return {"ok": True, "shop": (r or {}).get("shop", {})}
        except IntegracionError as e:
            self._audit(A.SHOPIFY_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Validación ──
    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.SHOPIFY_VALIDATE, id_empresa, usuario)
        url, token = self._config(id_empresa)
        comprob = {"url": "ok" if url else "falta", "token": "ok" if token else "falta",
                   "ssl": "ok" if (url or "").lower().startswith("https") else "aviso"}
        if not (url and token):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            r = self._req("GET", "shop.json", id_empresa)
            version = getattr(T.get_transporte(), "api_version", None) or T.API_VERSION
            comprob.update({"api": "ok", "permisos": "ok", "version": version or "?"})
            try:
                from src.services.marketplace.integraciones_comerciales import servicio
                servicio.validar(id_empresa, "shopify", usuario=usuario)   # estado existente → VALIDADA
            except Exception as e:
                logger.debug("estado validar shopify: %s", e)
            return {"ok": True, "estado": "VALIDADA", "version": version,
                    "shop": (r or {}).get("shop", {}), "comprobaciones": comprob}
        except IntegracionError as e:
            self._audit(A.SHOPIFY_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def obtener_version(self, *, id_empresa=None) -> str | None:
        return getattr(T.get_transporte(), "api_version", None) or T.API_VERSION

    # ── 4 · Importación (idempotente, reutiliza motores ERP) ──
    def importar_productos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.SHOPIFY_IMPORT, id_empresa, usuario, "productos")
        from src.db import catalogo as C
        extra = {"updated_at_min": _iso(desde)} if desde else None
        procesados, skus = 0, []
        for p in self._paginar("products", id_empresa, extra=extra):
            sku = _sku_de_producto(p)
            variantes = p.get("variants") or [{}]
            precio = _num(variantes[0].get("price"))
            try:
                C.upsert_producto(sku, id_empresa=id_empresa, nombre=p.get("title"))   # idempotente por SKU
                from src.db import articulos as ART
                ART.actualizar_precio(sku, precio)
            except Exception as e:
                logger.debug("upsert producto shopify %s: %s", sku, e)
            procesados += 1
            skus.append(sku)
        return {"ok": True, "procesados": procesados, "skus": skus}

    def importar_clientes(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.SHOPIFY_IMPORT, id_empresa, usuario, "clientes")
        from src.db import clientes as CL
        extra = {"updated_at_min": _iso(desde)} if desde else None
        creados = actualizados = 0
        for c in self._paginar("customers", id_empresa, extra=extra):
            email = (c.get("email") or "").strip()
            nombre = " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x).strip() or email
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
                logger.debug("importar cliente shopify %s: %s", email, e)
        return {"ok": True, "creados": creados, "actualizados": actualizados}

    def importar_pedidos(self, *, id_empresa=None, usuario=None, desde=None) -> dict:
        self._audit(A.SHOPIFY_IMPORT, id_empresa, usuario, "pedidos")
        from src.services.tpv import online_orders_service as OS
        extra = {"status": "any", "updated_at_min": _iso(desde)} if desde else {"status": "any"}
        creados = duplicados = 0
        for o in self._paginar("orders", id_empresa, extra=extra):
            ref = f"SHOPIFY-{o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            cli = o.get("customer") or {}
            cliente = {"nombre": " ".join(x for x in (cli.get("first_name"), cli.get("last_name")) if x)
                       or (o.get("email") or "Cliente Web"), "email": cli.get("email") or o.get("email"),
                       "telefono": cli.get("phone")}
            lineas = [{"codigo": (li.get("sku") or f"SHOPIFY-{li.get('product_id')}"),
                       "nombre": li.get("title") or li.get("name"), "cantidad": _num(li.get("quantity"), 1),
                       "precio": _num(li.get("price"))} for li in (o.get("line_items") or [])]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="shopify", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido shopify %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    # ── 5 · Exportación (solo productos de la empresa) ──
    def exportar_stock(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.SHOPIFY_EXPORT, id_empresa, usuario, "stock")
        from src.db import stock_almacen as SA
        n = 0
        for it in (articulos or []):
            sid = it.get("shopify_id")
            if not sid:
                continue
            stock = SA.stock_total_global(it.get("sku"), id_empresa=id_empresa) if it.get("sku") else 0
            variante = {"inventory_quantity": int(stock)}
            if it.get("variant_id"):
                variante["id"] = it["variant_id"]
            try:
                self._req("PUT", f"products/{sid}.json", id_empresa,
                          json={"product": {"id": sid, "variants": [variante]}})
                n += 1
            except Exception as e:
                logger.debug("exportar stock shopify %s: %s", sid, e)
        return {"ok": True, "exportados": n}

    def exportar_precios(self, *, id_empresa=None, usuario=None, articulos=None) -> dict:
        self._audit(A.SHOPIFY_EXPORT, id_empresa, usuario, "precios")
        n = 0
        for it in (articulos or []):
            sid = it.get("shopify_id")
            precio = it.get("precio")
            if not sid or precio is None:
                continue
            variante = {"price": str(_num(precio))}
            if it.get("variant_id"):
                variante["id"] = it["variant_id"]
            try:
                self._req("PUT", f"products/{sid}.json", id_empresa,
                          json={"product": {"id": sid, "variants": [variante]}})
                n += 1
            except Exception as e:
                logger.debug("exportar precio shopify %s: %s", sid, e)
        return {"ok": True, "exportados": n}

    # ── 7 · Estado de pedido (ERP → Shopify) ──
    def actualizar_estado_pedido(self, id_externo, estado_erp, *, id_empresa=None, usuario=None) -> dict:
        destino = _ESTADO_ERP_A_SHOPIFY.get(str(estado_erp).upper(), "open")
        sid = str(id_externo).replace("SHOPIFY-", "")
        try:
            if destino == "cancelled":
                self._req("POST", f"orders/{sid}/cancel.json", id_empresa)
            else:
                self._req("PUT", f"orders/{sid}.json", id_empresa,
                          json={"order": {"id": sid, "note": f"estado ERP: {estado_erp}"}})
            return {"ok": True, "estado_shopify": destino}
        except IntegracionError as e:
            self._audit(A.SHOPIFY_ERROR, id_empresa, usuario, e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 6 · Sincronización ──
    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.SHOPIFY_SYNC_START, id_empresa, usuario, "inicial")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.validar(id_empresa, "shopify", usuario=usuario)
            servicio.sincronizar(id_empresa, "shopify", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync shopify: %s", e)
        self._audit(A.SHOPIFY_SYNC_FINISH, id_empresa, usuario, "inicial")
        return {"ok": True, "resultado": res}

    def sincronizacion_incremental(self, *, id_empresa=None, usuario=None) -> dict:
        self._audit(A.SHOPIFY_SYNC_START, id_empresa, usuario, "incremental")
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        desde = None
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            i = servicio.obtener(id_empresa, "shopify") or {}
            desde = i.get("ultima_sync")
        except Exception:
            pass
        res = {"productos": self.importar_productos(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "clientes": self.importar_clientes(id_empresa=id_empresa, usuario=usuario, desde=desde),
               "pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario, desde=desde)}
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            servicio.sincronizar(id_empresa, "shopify", usuario=usuario)
        except Exception as e:
            logger.debug("estado sync inc shopify: %s", e)
        self._audit(A.SHOPIFY_SYNC_FINISH, id_empresa, usuario, "incremental")
        return {"ok": True, "desde": desde, "resultado": res}
