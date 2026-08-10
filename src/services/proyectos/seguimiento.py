"""
Seguimiento económico del proyecto: imputación de HORAS (con coste/hora) y COSTES extra, y cálculo de
RENTABILIDAD = presupuesto − (Σ horas×coste_hora + Σ costes). Multiempresa.
"""

import datetime as _dt
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion
from src.services.proyectos.proyectos import _emp, obtener_proyecto

logger = logging.getLogger("proyectos.seguimiento")


def registrar_horas(id_proyecto, horas, *, coste_hora=None, usuario=None, id_tarea=None, fecha=None,
                    descripcion=None, id_empresa=None):
    eid = _emp(id_empresa)
    try:
        horas = round(float(horas), 2)
    except (TypeError, ValueError):
        return None
    if horas <= 0:
        return None
    if coste_hora is None:                      # coste/hora por defecto del proyecto
        p = obtener_proyecto(id_proyecto, eid) or {}
        coste_hora = float(p.get("coste_hora_defecto") or 0)
    fecha = fecha or _dt.date.today().isoformat()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO proyecto_horas (id_empresa,id_proyecto,id_tarea,usuario,fecha,horas,"
                        "coste_hora,descripcion) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (eid, id_proyecto, id_tarea, usuario, fecha, horas, round(float(coste_hora), 2),
                         descripcion))
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar_horas: %s", e)
        return None


def listar_horas(id_proyecto, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proyecto_horas WHERE id_empresa=%s AND id_proyecto=%s ORDER BY fecha, id",
                        (_emp(id_empresa), id_proyecto))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_horas: %s", e)
        return []


def registrar_coste(id_proyecto, concepto, importe, *, tipo="gasto", fecha=None, id_empresa=None):
    concepto = (concepto or "").strip()
    if not concepto:
        return None
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return None
    fecha = fecha or _dt.date.today().isoformat()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO proyecto_costes (id_empresa,id_proyecto,concepto,importe,tipo,fecha) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (_emp(id_empresa), id_proyecto, concepto, importe, tipo, fecha))
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar_coste: %s", e)
        return None


def listar_costes(id_proyecto, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM proyecto_costes WHERE id_empresa=%s AND id_proyecto=%s ORDER BY fecha, id",
                        (_emp(id_empresa), id_proyecto))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_costes: %s", e)
        return []


def rentabilidad(id_proyecto, id_empresa=None):
    """Rentabilidad del proyecto: presupuesto vs coste real (horas×coste + costes extra)."""
    eid = _emp(id_empresa)
    p = obtener_proyecto(id_proyecto, eid)
    if not p:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(horas),0), COALESCE(SUM(horas*coste_hora),0) "
                        "FROM proyecto_horas WHERE id_empresa=%s AND id_proyecto=%s", (eid, id_proyecto))
            horas_tot, coste_horas = cur.fetchone()
            cur.execute("SELECT COALESCE(SUM(importe),0) FROM proyecto_costes WHERE id_empresa=%s AND "
                        "id_proyecto=%s", (eid, id_proyecto))
            coste_extra = cur.fetchone()[0]
    except Exception as e:
        logger.error("rentabilidad: %s", e)
        return None
    presupuesto = float(p.get("presupuesto") or 0)
    coste_horas = float(coste_horas or 0)
    coste_extra = float(coste_extra or 0)
    coste_total = round(coste_horas + coste_extra, 2)
    margen = round(presupuesto - coste_total, 2)
    return {
        "presupuesto": round(presupuesto, 2),
        "horas_totales": float(horas_tot or 0),
        "coste_horas": round(coste_horas, 2),
        "coste_extra": round(coste_extra, 2),
        "coste_total": coste_total,
        "margen": margen,
        "margen_pct": round(margen / presupuesto * 100, 1) if presupuesto else None,
    }
