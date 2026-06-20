"""
Capa de datos: EMPLEADOS / expediente laboral (F4.1.2). Multi-tenant.

Núcleo del expediente del trabajador (`rrhh_empleados`). Patrón idéntico a
`db.centros`/`db.representantes`: funciones CRUD + consultas. Identidad por NIF único
por empresa. `expediente()` agrega ficha + historiales (ver módulos hermanos).
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.empleados")

_PERMITIDOS = (
    "id_tienda", "id_usuario", "nombre", "apellidos", "sexo", "fecha_nacimiento",
    "nacionalidad", "nif", "num_ss", "direccion", "municipio", "provincia", "cp",
    "pais", "telefono", "email", "id_centro", "categoria", "grupo_prof", "convenio",
    "puesto", "salario_base", "jornada", "estado", "fecha_alta", "fecha_baja",
)


def crear_empleado(id_empresa=None, **campos) -> int | None:
    """Crea un empleado. Requiere `nombre` y `nif`. Devuelve el id o None."""
    id_empresa = id_empresa or empresa_actual_id()
    nombre = (campos.get("nombre") or "").strip()
    nif = (campos.get("nif") or "").strip().upper()
    if not nombre or not nif:
        logger.warning("crear_empleado: nombre y nif son obligatorios")
        return None
    datos = {k: campos.get(k) for k in _PERMITIDOS if k in campos}
    datos["nombre"] = nombre
    datos["nif"] = nif
    cols = ["id_empresa"] + list(datos.keys())
    vals = [id_empresa] + list(datos.values())
    ph = ", ".join(["%s"] * len(cols))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO rrhh_empleados ({', '.join(cols)}) VALUES ({ph})", vals)
            eid = cur.lastrowid
            conn.commit()
            return eid
    except Exception as e:
        logger.error("crear_empleado(%s): %s", nif, e)
        return None


def obtener_empleado(id_empleado, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_empleados WHERE id=%s AND id_empresa=%s",
                        (id_empleado, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_empleado(%s): %s", id_empleado, e)
        return None


def obtener_por_nif(nif, id_empresa=None) -> dict | None:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_empleados WHERE nif=%s AND id_empresa=%s",
                        ((nif or "").strip().upper(), id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_por_nif(%s): %s", nif, e)
        return None


def listar_empleados(id_empresa=None, estado=None, texto=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if texto:
        filtros.append("(nombre LIKE %s OR apellidos LIKE %s OR nif LIKE %s)")
        params += [f"%{texto}%"] * 3
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_empleados WHERE " + " AND ".join(filtros)
                        + " ORDER BY apellidos, nombre", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_empleados: %s", e)
        return []


def actualizar_empleado(id_empleado, id_empresa=None, **campos) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    sets = {k: campos[k] for k in _PERMITIDOS if k in campos}
    if "nif" in sets and sets["nif"]:
        sets["nif"] = str(sets["nif"]).strip().upper()
    if not sets:
        return False
    cols = ", ".join(f"{k}=%s" for k in sets)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE rrhh_empleados SET {cols} WHERE id=%s AND id_empresa=%s",
                        (*sets.values(), id_empleado, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_empleado(%s): %s", id_empleado, e)
        return False


def eliminar_empleado(id_empleado, id_empresa=None) -> bool:
    """Elimina el empleado y, en cascada, sus historiales (FK ON DELETE CASCADE)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM rrhh_empleados WHERE id=%s AND id_empresa=%s",
                        (id_empleado, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_empleado(%s): %s", id_empleado, e)
        return False


def expediente(id_empleado, id_empresa=None) -> dict | None:
    """Agrega la ficha del empleado + sus historiales (contratos, nóminas, vacaciones,
    ausencias, documentos). Solo lectura."""
    id_empresa = id_empresa or empresa_actual_id()
    ficha = obtener_empleado(id_empleado, id_empresa)
    if not ficha:
        return None
    from src.rrhh.db import (ausencias, contratos, documentos, nominas,
                             vacaciones)
    return {
        "empleado": ficha,
        "contratos": contratos.listar_contratos(id_empleado, id_empresa),
        "nominas": nominas.listar_nominas(id_empleado, id_empresa),
        "vacaciones": vacaciones.listar_vacaciones(id_empleado, id_empresa),
        "ausencias": ausencias.listar_ausencias(id_empleado, id_empresa),
        "documentos": documentos.listar_documentos(id_empleado, id_empresa),
    }
