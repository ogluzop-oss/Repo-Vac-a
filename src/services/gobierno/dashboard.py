"""
Dashboard directivo (Paquete Enterprise 7, SUBFASE 7.10). Indicadores ejecutivos de gobierno:
empresas/delegaciones/tiendas/usuarios, delegaciones activas, aprobaciones pendientes, escalados,
ausencias. Solo lectura; consultas agregadas (rendimiento). Complementa el Centro/BI.
"""

import logging

from src.services.gobierno import delegacion as _D
from src.services.gobierno import organigrama as _O

logger = logging.getLogger("gobierno.dashboard")


def _scalar(cur, sql, params):
    try:
        cur.execute(sql, params)
        r = cur.fetchone()
        return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
    except Exception:
        return 0


def indicadores(id_empresa=None) -> dict:
    emp = _O._emp(id_empresa)
    por_tipo = {}
    for n in _O.listar(emp):
        por_tipo[n["tipo"]] = por_tipo.get(n["tipo"], 0) + 1
    delegaciones_activas = len(_D.activas(emp))
    aprob_pend = escalados = 0
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            aprob_pend = _scalar(cur, "SELECT COUNT(*) FROM automatizaciones_ejecuciones "
                                 "WHERE id_empresa=%s AND estado='PENDIENTE'", (emp,))
            escalados = _scalar(cur, "SELECT COUNT(*) FROM org_escalados WHERE id_empresa=%s", (emp,))
    except Exception as e:
        logger.debug("indicadores: %s", e)
    return {
        "grupos": por_tipo.get("grupo", 0),
        "empresas": por_tipo.get("empresa", 0),
        "centrales": por_tipo.get("central", 0),
        "zonas": por_tipo.get("zona", 0),
        "delegaciones": por_tipo.get("delegacion", 0),
        "tiendas": por_tipo.get("tienda", 0),
        "almacenes": por_tipo.get("almacen", 0),
        "departamentos": por_tipo.get("departamento", 0),
        "usuarios": por_tipo.get("empleado", 0),
        "nodos_total": sum(por_tipo.values()),
        "delegaciones_activas": delegaciones_activas,
        "ausencias": delegaciones_activas,
        "aprobaciones_pendientes": aprob_pend,
        "escalados": escalados,
    }
