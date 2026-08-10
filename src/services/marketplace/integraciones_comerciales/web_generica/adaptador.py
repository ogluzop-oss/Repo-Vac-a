"""
Marketplace · Integraciones Comerciales · **Conector Web genérica / tradicional** — implementación REAL.

Para empresas que YA tienen una web hecha con OTRO proveedor (Wix, WordPress, Squarespace, web a medida…), en
DOS modos:

  · ``web_feed`` — **MODO A**: publicación de CATÁLOGO por FEED (JSON/CSV/XML) que la web consume. Operación
    LOCAL (sin red, SIN COSTE): reutiliza el PIM (`web_generica.feed`). ``disponible()`` = True (capacidad
    local; no requiere credenciales externas).
  · ``web_rest`` — **MODO B**: web con PUNTOS DE CONSUMO (endpoints REST). Cliente REST REAL y DEGRADABLE
    (transporte inyectable + token vía SecretManager); solo llama a la web del PROPIO cliente (sin APIs de
    pago). ``disponible()`` = bool(url y token). Importa pedidos y exporta stock/precios REUTILIZANDO los
    motores del ERP (`online_orders_service`, `db.catalogo`), sin duplicar lógica.

PREPARADO sobre el motor WEB-13 (sin modificarlo). Idempotente (dedup de pedidos por referencia externa),
multiempresa. Sin credenciales/URL → sin red (honesto).
"""

import logging
import os

from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    AdaptadorConector
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.motor.versiones import \
    VersionInfo
from src.services.marketplace.integraciones_comerciales.web_generica import \
    feed as _feed
from src.services.marketplace.integraciones_comerciales.web_generica import \
    secretos as _sec
from src.services.marketplace.integraciones_comerciales.web_generica import \
    transporte as _T

logger = logging.getLogger("marketplace.integraciones_comerciales.web_generica.adaptador")


def _num(v, defecto=0.0):
    try:
        return float(v)
    except Exception:
        return defecto


def _estado_motor(clave, id_empresa, usuario, accion):
    """Actualiza SOLO el estado existente del motor (VALIDADA/SINCRONIZADA); nunca crea estados nuevos."""
    try:
        from src.services.marketplace.integraciones_comerciales import servicio
        getattr(servicio, accion)(id_empresa, clave, usuario=usuario)
    except Exception as e:
        logger.debug("estado motor %s/%s: %s", clave, accion, e)


# ── MODO A — Feed de catálogo (local, sin coste) ──────────────────────────────
class WebFeedAdapter(AdaptadorConector):
    """MODO A — publicación de catálogo por FEED local (web tradicional SIN API)."""

    plataforma = "web_feed"
    modo = "feed"
    version = VersionInfo(api_version="feed/1", connector_version="1.0.0", minimum_version="1.0")

    def disponible(self, id_empresa=None) -> bool:
        # Capacidad LOCAL: siempre disponible (genera el feed desde el PIM, sin credenciales externas).
        return True

    def generar(self, *, id_empresa=None, formato="json", solo_visibles=False, usuario=None) -> dict:
        return _feed.generar_feed(id_empresa, formato=formato, solo_visibles=solo_visibles, usuario=usuario)

    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        prods = _feed.productos(id_empresa)
        ok = len(prods) > 0
        if ok:
            _estado_motor("web_feed", id_empresa, usuario, "validar")
        return {"ok": ok, "estado": "VALIDADA" if ok else None, "productos": len(prods),
                "comprobaciones": {"catalogo": "ok" if ok else "vacío"}}

    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None, formato="json") -> dict:
        r = self.generar(id_empresa=id_empresa, formato=formato, usuario=usuario)
        if r.get("ok"):
            _estado_motor("web_feed", id_empresa, usuario, "validar")
            _estado_motor("web_feed", id_empresa, usuario, "sincronizar")
        return r

    sincronizacion_incremental = sincronizacion_inicial


# ── MODO B — Web con endpoints REST (real, degradable) ────────────────────────
class WebRestAdapter(AdaptadorConector):
    """MODO B — web tradicional CON endpoints REST (recibe pedidos, exporta stock/precios)."""

    plataforma = "web_rest"
    modo = "rest"
    version = VersionInfo(api_version="rest/1", connector_version="1.0.0", minimum_version="1.0")

    def _integracion(self, id_empresa):
        try:
            from src.services.marketplace.integraciones_comerciales import servicio
            return servicio.obtener(id_empresa, "web_rest") if id_empresa is not None else None
        except Exception:
            return None

    def _config(self, id_empresa=None):
        i = self._integracion(id_empresa) or {}
        url = i.get("url") or os.getenv("WEB_REST_URL")
        ref = i.get("credenciales_ref") or "WEB_REST"
        return url, _sec.token(ref)

    def disponible(self, id_empresa=None) -> bool:
        url, tok = self._config(id_empresa)
        return bool(url and tok)

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["estado"] = "OPERATIVO" if self.disponible() else "PREPARADO"
        return d

    def _req(self, method, path, id_empresa=None, *, json=None, params=None):
        url, tok = self._config(id_empresa)
        if not (url and tok):
            raise IntegracionError(CodigoError.MISSING_CREDENTIALS,
                                   "URL/token de la web no configurados", plataforma="web_rest")
        return _T.get_transporte().request(method, url, path, token=tok, json=json, params=params)

    def validar(self, *, id_empresa=None, usuario=None) -> dict:
        url, tok = self._config(id_empresa)
        comprob = {"url": "ok" if url else "falta", "token": "ok" if tok else "falta",
                   "ssl": "ok" if (url or "").lower().startswith("https") else "aviso"}
        if not (url and tok):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value, "comprobaciones": comprob}
        try:
            self._req("GET", "productos", id_empresa, params={"limit": 1})
            comprob["api"] = "ok"
            _estado_motor("web_rest", id_empresa, usuario, "validar")
            return {"ok": True, "estado": "VALIDADA", "comprobaciones": comprob}
        except IntegracionError as e:
            return {"ok": False, **e.to_dict(), "comprobaciones": comprob}

    def importar_pedidos(self, *, id_empresa=None, usuario=None) -> dict:
        """Importa pedidos de la web al MISMO motor de pedidos del ERP (TPV/Portal Web/Canal Web)."""
        from src.services.tpv import online_orders_service as OS
        creados = duplicados = 0
        for o in (self._req("GET", "pedidos", id_empresa) or []):
            ref = f"WEB-{o.get('id')}"
            existe = any(str(p.get("referencia_externa")) == ref
                         for p in (OS.listar_pedidos_online(texto=ref) or []))
            if existe:
                duplicados += 1
                continue
            cli = o.get("cliente") or {}
            cliente = {"nombre": cli.get("nombre") or "Cliente Web", "email": cli.get("email"),
                       "telefono": cli.get("telefono")}
            lineas = [{"codigo": li.get("codigo") or li.get("sku"), "nombre": li.get("nombre"),
                       "cantidad": _num(li.get("cantidad"), 1), "precio": _num(li.get("precio"))}
                      for li in (o.get("lineas") or [])]
            if not lineas:
                continue
            try:
                OS.crear_pedido_online(cliente, lineas, plataforma="web_rest", referencia_externa=ref)
                creados += 1
            except Exception as e:
                logger.debug("crear pedido web %s: %s", ref, e)
        return {"ok": True, "creados": creados, "duplicados": duplicados}

    def exportar_stock(self, *, id_empresa=None, usuario=None) -> dict:
        """Exporta stock/precio de los productos de la empresa a la web (PUT /productos/{codigo})."""
        from src.db import catalogo as C
        n = 0
        for a in (C.articulos_para_catalogo(id_empresa=id_empresa) or []):
            if a.get("bloqueado"):
                continue
            try:
                self._req("PUT", f"productos/{a.get('codigo')}", id_empresa,
                          json={"stock": int(a.get("stock") or 0), "precio": _num(a.get("precio"))})
                n += 1
            except Exception as e:
                logger.debug("exportar stock web %s: %s", a.get("codigo"), e)
        return {"ok": True, "exportados": n}

    def sincronizacion_inicial(self, *, id_empresa=None, usuario=None) -> dict:
        if not self.disponible(id_empresa):
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value}
        res = {"pedidos": self.importar_pedidos(id_empresa=id_empresa, usuario=usuario),
               "stock": self.exportar_stock(id_empresa=id_empresa, usuario=usuario)}
        _estado_motor("web_rest", id_empresa, usuario, "validar")
        _estado_motor("web_rest", id_empresa, usuario, "sincronizar")
        return {"ok": True, "resultado": res}

    sincronizacion_incremental = sincronizacion_inicial
