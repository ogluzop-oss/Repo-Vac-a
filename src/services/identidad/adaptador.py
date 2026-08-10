"""
IOC v2 · Factory de adaptadores de identidad (Bloque III) — base HOMOGÉNEA y ÚNICA sobre la que se
construyen todos los adaptadores de módulo (`identidad_<mod>.py`), evitando duplicar código.

Cada adaptador de módulo se obtiene con `construir("<modulo>")` y ofrece exactamente la misma interfaz
que los adaptadores validados en CRM/Stock/Compras/Producción: `empresa_id`, `tienda_actual`,
`almacen_actual`, `empresa_tienda_almacen`, `contexto`, `identidad` (resolución significativa que
publica `<modulo>.identidad.resuelta`) y `telemetria`. Construido exclusivamente sobre `IdentityAPI`;
nunca Repository/Cache/SQL. Behavior-preserving (mismo `empresa_id` con *fallback*).
"""

import logging
import threading

logger = logging.getLogger("identidad.adaptador")


def _api():
    from src.services.identidad.api import api
    return api()


class _Adaptador:
    def __init__(self, modulo: str):
        self.modulo = modulo
        self._lock = threading.RLock()
        self._met = {"empresa_id": 0, "tienda_actual": 0, "almacen_actual": 0, "contexto": 0,
                     "identidad": 0, "errores": 0}

    # ── Camino caliente: resolución de empresa (sin eventos) ─────────────────
    def empresa_id(self, id_empresa=None):
        with self._lock:
            self._met["empresa_id"] += 1
        try:
            from src.services.identidad import _base as B
            eid = B.emp(id_empresa)
            if eid:
                return eid
        except Exception:
            pass
        try:
            from src.services.gemelo import fuentes
            return fuentes.emp(id_empresa)
        except Exception:
            return id_empresa

    def tienda_actual(self):
        with self._lock:
            self._met["tienda_actual"] += 1
        try:
            from src.db.empresa import tienda_actual_id
            return tienda_actual_id()
        except Exception:
            return None

    def almacen_actual(self):
        with self._lock:
            self._met["almacen_actual"] += 1
        try:
            from src.db.empresa import almacen_actual_id
            return almacen_actual_id()
        except Exception:
            return None

    def empresa_tienda_almacen(self, id_empresa=None):
        return self.empresa_id(id_empresa), self.tienda_actual(), self.almacen_actual()

    # ── Resoluciones significativas (IdentityContext + eventos) ──────────────
    def contexto(self, *, id_empresa=None, id_centro=None, id_tienda=None, id_almacen=None) -> dict:
        with self._lock:
            self._met["contexto"] += 1
        try:
            return _api().obtener_contexto(id_empresa=id_empresa, id_centro=id_centro,
                                           id_tienda=id_tienda, id_almacen=id_almacen)
        except Exception as e:
            with self._lock:
                self._met["errores"] += 1
            logger.debug("[%s] contexto: %s", self.modulo, e)
            return {"id_empresa": self.empresa_id(id_empresa), "id_tienda": id_tienda,
                    "id_almacen": id_almacen}

    def identidad(self, ref_entidad, ref_id=None, *, id_tienda=None, id_almacen=None, id_empresa=None):
        """Resolución significativa: devuelve IdentityResult y publica `<modulo>.identidad.resuelta`."""
        with self._lock:
            self._met["identidad"] += 1
        eid = self.empresa_id(id_empresa)
        try:
            res = _api().resolver(id_empresa=eid, id_tienda=id_tienda, id_almacen=id_almacen)
            try:
                from src.services import eventos
                eventos.publicar(f"{self.modulo}.identidad.resuelta", id_empresa=eid,
                                 ref_entidad=ref_entidad, ref_id=ref_id,
                                 payload={"origen": self.modulo, "id_tienda": id_tienda,
                                          "id_almacen": id_almacen})
            except Exception:
                pass
            return res
        except Exception as e:
            with self._lock:
                self._met["errores"] += 1
            logger.debug("[%s] identidad: %s", self.modulo, e)
            return None

    def telemetria(self) -> dict:
        with self._lock:
            propio = dict(self._met)
        try:
            return {f"{self.modulo}_adaptador": propio, "identity_api": _api().telemetria()}
        except Exception:
            return {f"{self.modulo}_adaptador": propio}


_REG = {}
_REG_LOCK = threading.RLock()


def construir(modulo: str) -> _Adaptador:
    """Devuelve (creando si es necesario) el adaptador homogéneo del módulo. Idempotente."""
    with _REG_LOCK:
        if modulo not in _REG:
            _REG[modulo] = _Adaptador(modulo)
        return _REG[modulo]
