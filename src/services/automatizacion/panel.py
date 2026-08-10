"""
Panel de automatizaciones (Paquete Enterprise 4, SUBFASE 4.9/4.10). Datos para la seccion del
Centro de Actividad: ejecutadas/pendientes/rechazadas/aprobadas/fallidas, tiempo ahorrado, ultima
ejecucion, y el detalle explicable de cada ejecucion (por que/regla/evento/prediccion/usuario/fecha).
Solo lectura sobre automatizaciones_ejecuciones.
"""

import logging

logger = logging.getLogger("automatizacion.panel")

_MIN_AHORRO = 5   # minutos estimados ahorrados por accion automatizada


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


def resumen(id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    counts, ultima = {}, None
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT estado, COUNT(*) FROM automatizaciones_ejecuciones WHERE id_empresa=%s "
                        "GROUP BY estado", (emp,))
            for r in cur.fetchall():
                g = (lambda i: r[i] if not isinstance(r, dict) else list(r.values())[i])
                counts[g(0)] = int(g(1))
            cur.execute("SELECT MAX(creado) FROM automatizaciones_ejecuciones WHERE id_empresa=%s", (emp,))
            r = cur.fetchone()
            ultima = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception as e:
        logger.error("resumen: %s", e)
    ejecutadas = counts.get("EJECUTADA", 0) + counts.get("PROPUESTA", 0) + counts.get("INFORMADA", 0)
    return {
        "ejecutadas": counts.get("EJECUTADA", 0),
        "propuestas": counts.get("PROPUESTA", 0),
        "informadas": counts.get("INFORMADA", 0),
        "pendientes": counts.get("PENDIENTE", 0),
        "aprobadas": counts.get("APROBADA", 0),
        "rechazadas": counts.get("RECHAZADA", 0),
        "fallidas": counts.get("FALLIDA", 0),
        "total": sum(counts.values()),
        "tiempo_ahorrado_min": ejecutadas * _MIN_AHORRO,
        "ultima_ejecucion": ultima,
    }


def listar(id_empresa=None, limite=50) -> list:
    """Ejecuciones recientes con su EXPLICABILIDAD completa (SUBFASE 4.10)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM automatizaciones_ejecuciones WHERE id_empresa=%s "
                        "ORDER BY id DESC LIMIT %s", (emp, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar: %s", e)
        return []
