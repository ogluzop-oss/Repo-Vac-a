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


def listar_por_tabla(tablas, desde=None, hasta=None, accion_like=None, id_empresa=None,
                     limite=500) -> list:
    """Entradas de auditoría cuya `tabla_afectada` esté en `tablas` (lista de nombres), opcionalmente
    acotadas por fecha (`desde`/`hasta`, 'YYYY-MM-DD') y/o un patrón adicional sobre `accion`
    (`accion_like`, p. ej. 'LOGIN%' — combinado con OR sobre `tablas`). Devuelve dicts (fecha,
    usuario, accion, tabla_afectada, detalles), más recientes primero."""
    tablas = list(tablas or [])
    if not tablas and not accion_like:
        return []
    cond, params = [], []
    if tablas:
        marcas = ",".join(["%s"] * len(tablas))
        cond.append(f"tabla_afectada IN ({marcas})")
        params += tablas
    if accion_like:
        cond.append("accion LIKE %s")
        params.append(accion_like)
    where = "(" + " OR ".join(cond) + ")"
    if id_empresa:
        where += " AND id_empresa=%s"; params.append(id_empresa)
    if desde:
        where += " AND fecha >= %s"; params.append(desde)
    if hasta:
        where += " AND fecha <= %s"; params.append(f"{hasta} 23:59:59")
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(f"SELECT fecha, usuario, accion, tabla_afectada, detalles FROM "
                        f"auditoria_logs WHERE {where} ORDER BY fecha DESC LIMIT %s",
                        params + [int(limite)])
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_por_tabla: %s", e)
        return []
