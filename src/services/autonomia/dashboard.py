"""
Dashboard de autonomia supervisada (Paquete Enterprise 10, SUBFASE 10.11). Backend del panel:
planes pendientes/aprobados/ejecutados/cancelados, reversiones, tiempo ahorrado y nivel de
automatizacion. Solo lectura y agregado sobre exec_planes/exec_acciones.
"""

import logging

from src.services.autonomia import indicador
from src.services.autonomia import modelo as M

logger = logging.getLogger("autonomia.dashboard")


def _emp(id_empresa=None):
    from src.services.autonomia import modos
    return modos._emp(id_empresa)


def _c(cur, sql, params):
    try:
        cur.execute(sql, params)
        r = cur.fetchone()
        return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
    except Exception:
        return 0


def panel(id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    por_estado = {}
    tiempo_ahorrado = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            for est in (M.BORRADOR, M.PENDIENTE_APROBACION, M.APROBADO, M.EN_EJECUCION,
                        M.EJECUTADO, M.PARCIAL, M.CANCELADO, M.REVERTIDO):
                por_estado[est] = _c(cur, "SELECT COUNT(*) FROM exec_planes WHERE id_empresa=%s "
                                     "AND estado=%s", (emp, est))
            # Tiempo ahorrado (proxy): 5 min por accion ejecutada automaticamente.
            ejec = _c(cur, "SELECT COUNT(*) FROM exec_acciones WHERE id_empresa=%s AND estado='EJECUTADA'", (emp,))
            tiempo_ahorrado = ejec * 5
    except Exception as e:
        logger.debug("panel autonomia: %s", e)

    ind = indicador.nivel(emp)
    return {
        "planes_pendientes": por_estado.get(M.PENDIENTE_APROBACION, 0) + por_estado.get(M.BORRADOR, 0),
        "planes_aprobados": por_estado.get(M.APROBADO, 0),
        "planes_ejecutados": por_estado.get(M.EJECUTADO, 0) + por_estado.get(M.PARCIAL, 0),
        "planes_cancelados": por_estado.get(M.CANCELADO, 0),
        "reversiones": por_estado.get(M.REVERTIDO, 0),
        "por_estado": por_estado,
        "tiempo_ahorrado_min": tiempo_ahorrado,
        "nivel_automatizacion_pct": ind["nivel_automatizacion_pct"],
        "modo_empresa": ind["modo_empresa"],
        "indicador": ind,
    }
