"""Consultas de solo LECTURA sobre el registro de auditoría (`auditoria_logs`).

La ESCRITURA de auditoría vive en `db.conexion.log_auditoria` (fuente única). Este módulo expone las
lecturas para que la GUI no consulte la tabla con SQL directo (Fase 3 · cliente fino).
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("auditoria.db")


def listar_por_prefijos(prefijos, limite=500) -> list:
    """Entradas de auditoría cuya `accion` empieza por alguno de los `prefijos`. Devuelve dicts
    (fecha, usuario, accion, detalles), más recientes primero."""
    prefijos = list(prefijos or [])
    if not prefijos:
        return []
    try:
        like = " OR ".join(["accion LIKE %s"] * len(prefijos))
        params = [f"{p}%" for p in prefijos]
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"SELECT fecha, usuario, accion, detalles FROM auditoria_logs "
                        f"WHERE ({like}) ORDER BY fecha DESC LIMIT %s", params + [int(limite)])
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_por_prefijos: %s", e)
        return []
