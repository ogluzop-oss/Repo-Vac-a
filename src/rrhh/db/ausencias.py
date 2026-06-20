"""
Capa de datos: HISTORIAL DE AUSENCIAS (`rrhh_ausencias`) — F4.1.2. Multi-tenant.

Bajas médicas, permisos y ausencias justificadas/injustificadas. Patrón CRUD.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.ausencias")

_PERMITIDOS = ("tipo", "fecha_inicio", "fecha_fin", "dias", "motivo", "justificada",
               "ref_documento")


def crear_ausencia(id_empleado, id_empresa=None, **campos) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    cols = ["id_empresa", "id_empleado"] + list(datos.keys())
    vals = [id_empresa, id_empleado] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_ausencias ({', '.join(cols)}) VALUES ({ph})", vals)
            aid = cur.lastrowid
            conn.commit()
            return aid
    except Exception as e:
        logger.error("crear_ausencia(emp=%s): %s", id_empleado, e)
        return None


def obtener_ausencia(id_aus, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_ausencias WHERE id=%s AND id_empresa=%s",
                        (id_aus, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_ausencia(%s): %s", id_aus, e)
        return None


def listar_ausencias(id_empleado, id_empresa=None, tipo=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    filtros, params = ["id_empleado=%s", "id_empresa=%s"], [id_empleado, id_empresa]
    if tipo:
        filtros.append("tipo=%s"); params.append(tipo)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_ausencias WHERE " + " AND ".join(filtros)
                        + " ORDER BY fecha_inicio DESC, id DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_ausencias(%s): %s", id_empleado, e)
        return []


def actualizar_ausencia(id_aus, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_ausencias SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_aus, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_ausencia(%s): %s", id_aus, e)
        return False


def eliminar_ausencia(id_aus, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_ausencias WHERE id=%s AND id_empresa=%s",
                        (id_aus, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_ausencia(%s): %s", id_aus, e)
        return False
