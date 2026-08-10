"""
Adaptador Smart Stock ↔ IOC (Bloque III.2) — punto oficial por el que Smart Stock resuelve identidad
a través de la `IdentityAPI`. Patrón Strangler, behavior-preserving. A diferencia del CRM, el stock
necesita empresa **y** tienda, por lo que el adaptador ofrece ambas resoluciones y el `IdentityContext`
completo (empresa/grupo/centro/tienda/almacén) para las operaciones que lo requieran.

Reglas:
- Smart Stock NO accede a SQL/Repository/Cache/tablas IOC para identidad: usa este adaptador.
- Dirección de dependencia correcta: Stock → IOC (este módulo importa IOC; IOC nunca importa Stock).
- Multiempresa: siempre se resuelve `id_empresa`; sin fugas entre empresas.
- Eventos/telemetría: solo en resoluciones SIGNIFICATIVAS (no en el camino caliente empresa/tienda).
- NO modifica ninguna lógica de inventario.
"""

import logging
import threading

logger = logging.getLogger("stock.identidad")

_LOCK = threading.RLock()
_MET = {"empresa_id": 0, "tienda_actual": 0, "contexto": 0, "identidad_almacen": 0, "errores": 0}


def _api():
    from src.services.identidad.api import api
    return api()


# ── Resolución de empresa (camino caliente; sustituye a los _emp del stock) ───
def empresa_id(id_empresa=None):
    """Resuelve la empresa activa a través de la capa de identidad IOC. Comportamiento IDÉNTICO al
    seam histórico (`fuentes.emp`), con *fallback* exacto. Camino caliente: sin eventos."""
    with _LOCK:
        _MET["empresa_id"] += 1
    try:
        from src.services.identidad import _base as B
        eid = B.emp(id_empresa)
        if eid:
            return eid
    except Exception:
        pass
    # Fallback histórico exacto (fuentes.emp incluye el fallback profundo a EMPRESA_DEFAULT_ID).
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


# ── Resolución de tienda (contexto activo; behavior-preserving) ───────────────
def tienda_actual():
    """Tienda activa (equivalente a `db.empresa.tienda_actual_id()`), centralizada + telemetría."""
    with _LOCK:
        _MET["tienda_actual"] += 1
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


def tienda_actual_int():
    """Tienda activa como entero (equivalente a `db.empresa.tienda_actual_id_int()`)."""
    with _LOCK:
        _MET["tienda_actual"] += 1
    try:
        from src.db.empresa import tienda_actual_id_int
        return tienda_actual_id_int()
    except Exception:
        return 0


def empresa_y_tienda(id_empresa=None):
    """(empresa, tienda) — para los seams de kardex/lotes/mermas. Comportamiento idéntico al histórico."""
    return empresa_id(id_empresa), tienda_actual()


# ── Resoluciones significativas (IdentityContext + eventos) ───────────────────
def contexto(*, id_empresa=None, id_centro=None, id_tienda=None, id_almacen=None) -> dict:
    """IdentityContext completo (empresa/grupo/centro/tienda/almacén) vía IdentityAPI. Uso: cuando una
    operación de stock necesita la identidad del origen/destino (traspaso, recepción, documento…)."""
    with _LOCK:
        _MET["contexto"] += 1
    try:
        return _api().obtener_contexto(id_empresa=id_empresa, id_centro=id_centro,
                                       id_tienda=id_tienda, id_almacen=id_almacen)
    except Exception as e:
        with _LOCK:
            _MET["errores"] += 1
        logger.debug("contexto: %s", e)
        return {"id_empresa": empresa_id(id_empresa), "id_tienda": id_tienda, "id_almacen": id_almacen}


def identidad_almacen(id_almacen=None, *, id_tienda=None, id_empresa=None):
    """Resuelve la identidad (contexto) asociada a un almacén/tienda de una operación de stock.
    Operación 'relevante': publica `stock.identidad.resuelta` y cuenta en telemetría."""
    with _LOCK:
        _MET["identidad_almacen"] += 1
    eid = empresa_id(id_empresa)
    try:
        res = _api().resolver(id_empresa=eid, id_tienda=id_tienda, id_almacen=id_almacen)
        try:
            from src.services import eventos
            eventos.publicar("stock.identidad.resuelta", id_empresa=eid, ref_entidad="almacen",
                             ref_id=id_almacen, payload={"id_tienda": id_tienda, "origen": "stock"})
        except Exception:
            pass
        return res
    except Exception as e:
        with _LOCK:
            _MET["errores"] += 1
        logger.debug("identidad_almacen: %s", e)
        return None


def telemetria() -> dict:
    """Telemetría combinada: contadores del adaptador Stock + snapshot de IdentityAPI."""
    with _LOCK:
        propio = dict(_MET)
    try:
        return {"stock_adaptador": propio, "identity_api": _api().telemetria()}
    except Exception:
        return {"stock_adaptador": propio}
