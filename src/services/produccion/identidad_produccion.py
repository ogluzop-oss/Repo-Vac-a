"""
Adaptador Producción ↔ IOC (Bloque III.4) — punto oficial por el que Producción (MRP/Fabricación)
resuelve identidad a través de la `IdentityAPI`. Construido con la misma estructura que
`identidad_crm.py`, `identidad_stock.py` e `identidad_compras.py`. Patrón Strangler, behavior-preserving.

Reglas:
- Producción NO accede a SQL/Repository/Cache/tablas IOC para identidad: usa este adaptador.
- Dirección: Producción → IdentityAPI → Service → Repository → Cache → IOC.
- Multiempresa: siempre se resuelve `id_empresa`; sin fugas entre empresas.
- Eventos/telemetría: solo en resoluciones SIGNIFICATIVAS (nunca en el camino caliente empresa/tienda).
- NO modifica ninguna lógica de producción (órdenes/operaciones/planificación/…) ni la GUI.
"""

import logging
import threading

logger = logging.getLogger("produccion.identidad")

_LOCK = threading.RLock()
_MET = {"empresa_id": 0, "tienda_actual": 0, "almacen_actual": 0, "contexto": 0,
        "identidad_orden": 0, "identidad_maquina": 0, "identidad_linea": 0,
        "identidad_operacion": 0, "errores": 0}


def _api():
    from src.services.identidad.api import api
    return api()


# ── Resolución de empresa (camino caliente; sustituye a los _emp de MRP) ──────
def empresa_id(id_empresa=None):
    """Empresa activa vía la capa de identidad IOC. Comportamiento IDÉNTICO al seam histórico, con
    *fallback* exacto. Camino caliente: sin eventos."""
    with _LOCK:
        _MET["empresa_id"] += 1
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


# ── Tienda / almacén activos (contexto; behavior-preserving) ──────────────────
def tienda_actual():
    with _LOCK:
        _MET["tienda_actual"] += 1
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


def almacen_actual():
    with _LOCK:
        _MET["almacen_actual"] += 1
    try:
        from src.db.empresa import almacen_actual_id  # opcional según versión del ERP
        return almacen_actual_id()
    except Exception:
        return None


def empresa_tienda_almacen(id_empresa=None):
    return empresa_id(id_empresa), tienda_actual(), almacen_actual()


# ── Resoluciones significativas (IdentityContext + eventos) ───────────────────
def contexto(*, id_empresa=None, id_centro=None, id_tienda=None, id_almacen=None) -> dict:
    """IdentityContext completo (empresa/grupo/centro/tienda/almacén) vía IdentityAPI."""
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


def _resolver_significativo(evento, ref_entidad, ref_id, *, id_tienda=None, id_almacen=None,
                           id_empresa=None):
    eid = empresa_id(id_empresa)
    try:
        res = _api().resolver(id_empresa=eid, id_tienda=id_tienda, id_almacen=id_almacen)
        try:
            from src.services import eventos
            eventos.publicar(evento, id_empresa=eid, ref_entidad=ref_entidad, ref_id=ref_id,
                             payload={"id_tienda": id_tienda, "id_almacen": id_almacen,
                                      "origen": "produccion"})
        except Exception:
            pass
        return res
    except Exception as e:
        with _LOCK:
            _MET["errores"] += 1
        logger.debug("_resolver_significativo(%s): %s", evento, e)
        return None


def identidad_orden(id_orden=None, *, id_almacen=None, id_empresa=None):
    """Identidad (empresa/almacén) de una orden de fabricación. Publica `produccion.identidad.orden`."""
    with _LOCK:
        _MET["identidad_orden"] += 1
    return _resolver_significativo("produccion.identidad.orden", "orden_fabricacion", id_orden,
                                   id_almacen=id_almacen, id_empresa=id_empresa)


def identidad_maquina(id_maquina=None, *, id_empresa=None):
    """Identidad de una máquina/estación. Publica `produccion.identidad.resuelta`."""
    with _LOCK:
        _MET["identidad_maquina"] += 1
    return _resolver_significativo("produccion.identidad.resuelta", "maquina", id_maquina,
                                   id_empresa=id_empresa)


def identidad_linea(id_linea=None, *, id_empresa=None):
    """Identidad de una línea de producción. Publica `produccion.identidad.resuelta`."""
    with _LOCK:
        _MET["identidad_linea"] += 1
    return _resolver_significativo("produccion.identidad.resuelta", "linea_produccion", id_linea,
                                   id_empresa=id_empresa)


def identidad_operacion(id_operacion=None, *, id_orden=None, id_empresa=None):
    """Identidad de una operación de ruta/parte de trabajo. Publica `produccion.identidad.operacion`."""
    with _LOCK:
        _MET["identidad_operacion"] += 1
    res = _resolver_significativo("produccion.identidad.operacion", "operacion_produccion",
                                  id_operacion, id_empresa=id_empresa)
    return res


def telemetria() -> dict:
    """Telemetría combinada: contadores del adaptador Producción + snapshot de IdentityAPI."""
    with _LOCK:
        propio = dict(_MET)
    try:
        return {"produccion_adaptador": propio, "identity_api": _api().telemetria()}
    except Exception:
        return {"produccion_adaptador": propio}
