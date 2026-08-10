"""
Resolucion de conflictos de sincronizacion (Fase 2, SUBFASE 2.7).

Estrategias: ultima_modificacion | prioridad_central | version_superior | timestamp.
Nunca se sobrescribe sin conocer la version. Cada conflicto queda registrado.
"""

import logging

logger = logging.getLogger("distribucion.conflictos")

ESTRATEGIAS = ("ultima_modificacion", "prioridad_central", "version_superior", "timestamp")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _registrar(emp, entidad, entidad_id, estrategia, vloc, vrem, resolucion, detalle):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO distribucion_conflictos (id_empresa, entidad, entidad_id, "
                        "estrategia, version_local, version_remota, resolucion, detalle) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, str(entidad), str(entidad_id), estrategia, vloc, vrem, resolucion,
                         (detalle or "")[:255]))
            c.commit()
    except Exception as e:
        logger.error("registrar conflicto: %s", e)


def resolver(entidad, entidad_id, *, version_local=None, version_remota=None,
             ts_local=None, ts_remota=None, origen_remoto=None, estrategia=None,
             id_empresa=None) -> str:
    """Devuelve 'local' o 'remoto' (quien gana) y registra el conflicto. Ante empate, gana
    el remoto/central (la central es la fuente de verdad por defecto)."""
    emp = _emp(id_empresa)
    if estrategia not in ESTRATEGIAS:
        try:
            from src.services.distribucion import config as _cfg
            estrategia = _cfg.obtener(emp).get("estrategia_conflicto") or "version_superior"
        except Exception:
            estrategia = "version_superior"

    if estrategia == "version_superior":
        gana = "remoto" if (version_remota or 0) >= (version_local or 0) else "local"
    elif estrategia == "prioridad_central":
        gana = "remoto" if str(origen_remoto or "").lower() == "central" else "local"
    else:  # ultima_modificacion | timestamp
        gana = "remoto" if (ts_remota or 0) >= (ts_local or 0) else "local"

    _registrar(emp, entidad, entidad_id, estrategia, version_local, version_remota, gana,
               f"origen_remoto={origen_remoto}")
    return gana
