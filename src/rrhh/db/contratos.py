"""
Capa de datos: HISTORIAL CONTRACTUAL (`rrhh_contratos`) — F4.1.2. Multi-tenant.

Contratos, renovaciones, modificaciones y anexos vinculados al expediente del
trabajador. Patrón CRUD idéntico a db.centros.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.contratos")

_PERMITIDOS = ("tipo_registro", "modalidad", "fecha_inicio", "fecha_fin", "salario",
               "jornada", "id_centro", "ref_documento", "datos_snapshot", "estado")


def crear_contrato(id_empleado, id_empresa=None, **campos) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    cols = ["id_empresa", "id_empleado"] + list(datos.keys())
    vals = [id_empresa, id_empleado] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_contratos ({', '.join(cols)}) VALUES ({ph})", vals)
            cid = cur.lastrowid
            conn.commit()
            return cid
    except Exception as e:
        logger.error("crear_contrato(emp=%s): %s", id_empleado, e)
        return None


def obtener_contrato(id_contrato, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_contratos WHERE id=%s AND id_empresa=%s",
                        (id_contrato, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_contrato(%s): %s", id_contrato, e)
        return None


def listar_contratos(id_empleado, id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_contratos WHERE id_empleado=%s AND id_empresa=%s "
                        "ORDER BY fecha_inicio DESC, id DESC", (id_empleado, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_contratos(%s): %s", id_empleado, e)
        return []


def actualizar_contrato(id_contrato, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_contratos SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_contrato, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_contrato(%s): %s", id_contrato, e)
        return False


def eliminar_contrato(id_contrato, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_contratos WHERE id=%s AND id_empresa=%s",
                        (id_contrato, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_contrato(%s): %s", id_contrato, e)
        return False
