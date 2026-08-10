"""
Indicador de autonomia (Paquete Enterprise 10, SUBFASE 10.12). Calcula el nivel de automatizacion
REAL de la empresa: basado UNICAMENTE en acciones realmente ejecutadas por el sistema, nunca en
estimaciones. nivel = acciones_auto_ejecutadas / (auto_ejecutadas + propuestas/manuales).
Solo lectura sobre exec_acciones.
"""

import logging

logger = logging.getLogger("autonomia.indicador")


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


def nivel(id_empresa=None, *, dias=90) -> dict:
    emp = _emp(id_empresa)
    ejecutadas = propuestas = revertidas = total = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            base = ("FROM exec_acciones WHERE id_empresa=%s AND creado >= (NOW() - INTERVAL %s DAY)")
            ejecutadas = _c(cur, f"SELECT COUNT(*) {base} AND estado='EJECUTADA'", (emp, dias))
            propuestas = _c(cur, f"SELECT COUNT(*) {base} AND estado IN ('OMITIDA','PENDIENTE')", (emp, dias))
            revertidas = _c(cur, f"SELECT COUNT(*) {base} AND estado='REVERTIDA'", (emp, dias))
            total = _c(cur, f"SELECT COUNT(*) {base}", (emp, dias))
    except Exception as e:
        logger.debug("nivel autonomia: %s", e)

    base_calc = ejecutadas + propuestas
    pct = round((ejecutadas / base_calc * 100), 1) if base_calc else 0.0
    from src.services.autonomia import modos
    modo = modos.obtener(emp)
    return {
        "nivel_automatizacion_pct": pct,
        "acciones_ejecutadas": ejecutadas,
        "acciones_propuestas": propuestas,
        "acciones_revertidas": revertidas,
        "acciones_total": total,
        "modo_empresa": modo,
        "periodo_dias": dias,
        "base": "acciones realmente ejecutadas (no estimaciones)",
    }
