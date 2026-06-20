"""
Capa de datos: VÍNCULO DOCUMENTAL RRHH (`rrhh_documentos`) — F4.1.2. Multi-tenant.

Enlace genérico documento↔expediente con snapshot de los datos usados al generar
(para que la información dejara de perderse). El cableado de los generadores con esta
tabla se hará en una fase posterior; aquí solo se ofrece la persistencia. Patrón CRUD.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.documentos")

_PERMITIDOS = ("tipo_doc", "fecha", "ref_documento", "datos_snapshot")


def crear_documento(id_empleado, id_empresa=None, **campos) -> int | None:
    id_empresa = id_empresa or empresa_actual_id()
    if not campos.get("tipo_doc"):
        logger.warning("crear_documento: tipo_doc obligatorio")
        return None
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    cols = ["id_empresa", "id_empleado"] + list(datos.keys())
    vals = [id_empresa, id_empleado] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_documentos ({', '.join(cols)}) VALUES ({ph})", vals)
            did = cur.lastrowid
            conn.commit()
            return did
    except Exception as e:
        logger.error("crear_documento(emp=%s): %s", id_empleado, e)
        return None


def obtener_documento(id_doc, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_documentos WHERE id=%s AND id_empresa=%s",
                        (id_doc, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_documento(%s): %s", id_doc, e)
        return None


def listar_documentos(id_empleado, id_empresa=None, tipo_doc=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    filtros, params = ["id_empleado=%s", "id_empresa=%s"], [id_empleado, id_empresa]
    if tipo_doc:
        filtros.append("tipo_doc=%s"); params.append(tipo_doc)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_documentos WHERE " + " AND ".join(filtros)
                        + " ORDER BY fecha DESC, id DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_documentos(%s): %s", id_empleado, e)
        return []


def actualizar_documento(id_doc, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_documentos SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_doc, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_documento(%s): %s", id_doc, e)
        return False


def eliminar_documento(id_doc, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_documentos WHERE id=%s AND id_empresa=%s",
                        (id_doc, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_documento(%s): %s", id_doc, e)
        return False
