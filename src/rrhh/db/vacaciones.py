"""
Capa de datos: HISTORIAL DE VACACIONES (`rrhh_vacaciones`) — F4.1.2. Multi-tenant.

Persistencia preparada para saldo/solicitudes/aprobaciones (la gestión completa
llega en F4.4). Patrón CRUD.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.vacaciones")

_PERMITIDOS = ("anio", "tipo", "fecha_inicio", "fecha_fin", "dias", "estado",
               "aprobado_por", "ref_documento")


def crear_vacaciones(id_empleado, id_empresa=None, **campos) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    if not campos.get("anio"):
        logger.warning("crear_vacaciones: anio obligatorio")
        return None
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    cols = ["id_empresa", "id_empleado"] + list(datos.keys())
    vals = [id_empresa, id_empleado] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_vacaciones ({', '.join(cols)}) VALUES ({ph})", vals)
            vid = cur.lastrowid
            conn.commit()
            return vid
    except Exception as e:
        logger.error("crear_vacaciones(emp=%s): %s", id_empleado, e)
        return None


def obtener_vacaciones(id_vac, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_vacaciones WHERE id=%s AND id_empresa=%s",
                        (id_vac, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_vacaciones(%s): %s", id_vac, e)
        return None


def listar_vacaciones(id_empleado, id_empresa=None, anio=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    filtros, params = ["id_empleado=%s", "id_empresa=%s"], [id_empleado, id_empresa]
    if anio:
        filtros.append("anio=%s"); params.append(int(anio))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_vacaciones WHERE " + " AND ".join(filtros)
                        + " ORDER BY anio DESC, fecha_inicio DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_vacaciones(%s): %s", id_empleado, e)
        return []


def actualizar_vacaciones(id_vac, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_vacaciones SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_vac, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_vacaciones(%s): %s", id_vac, e)
        return False


def eliminar_vacaciones(id_vac, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_vacaciones WHERE id=%s AND id_empresa=%s",
                        (id_vac, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_vacaciones(%s): %s", id_vac, e)
        return False
