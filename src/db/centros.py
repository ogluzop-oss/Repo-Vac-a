"""
Capa de datos: CENTROS DE TRABAJO de la empresa (multi-tenant).

Tabla independiente `centros_trabajo` relacionada con `empresas` por `id_empresa`
(y opcionalmente con una tienda por `id_tienda`, sin asumir relación 1:1). Un
centro puede ser una tienda, una oficina, un almacén, una sede logística, etc.
Forma parte de la fuente única de datos corporativos; los documentos lo consumen
vía `empresa.datos_corporativos()` ([[project_multitenant]]).
"""

import logging
import uuid

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("centros_db")

_PERMITIDOS = (
    "id_tienda", "nombre_centro", "direccion", "codigo_postal", "municipio",
    "provincia", "comunidad_autonoma", "pais", "telefono", "email",
    "codigo_cuenta_cotizacion", "codigo_centro_trabajo", "actividad_economica",
    "cod_pais", "cod_municipio",
    "es_principal", "estado",
)


def _siguiente_codigo(cur, id_empresa) -> str:
    cur.execute(
        "SELECT codigo_centro FROM centros_trabajo WHERE id_empresa=%s AND codigo_centro LIKE 'CDT-%%' "
        "ORDER BY codigo_centro DESC LIMIT 1",
        (id_empresa,),
    )
    row = cur.fetchone()
    ultimo = 0
    if row:
        val = row[0] if not isinstance(row, dict) else row["codigo_centro"]
        try:
            ultimo = int(str(val).split("-")[-1])
        except (ValueError, IndexError):
            ultimo = 0
    return f"CDT-{ultimo + 1:03d}"


def listar_centros(id_empresa=None, solo_activos=True) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = "SELECT * FROM centros_trabajo WHERE id_empresa=%s"
            if solo_activos:
                sql += " AND estado='activo'"
            sql += " ORDER BY es_principal DESC, fecha_alta ASC"
            cur.execute(sql, (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_centros: %s", e)
        return []


def obtener_centro(id_centro) -> dict | None:
    if not id_centro:
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM centros_trabajo WHERE id_centro=%s", (id_centro,))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_centro(%s): %s", id_centro, e)
        return None


def centro_principal(id_empresa=None, id_tienda=None) -> dict | None:
    """Centro principal de la empresa; si se pasa id_tienda, prioriza el de esa
    tienda. Si no hay marcado principal, devuelve el primero activo."""
    id_empresa = id_empresa or empresa_actual_id()
    centros = listar_centros(id_empresa, solo_activos=True)
    if not centros:
        return None
    if id_tienda is not None:
        de_tienda = [c for c in centros if c.get("id_tienda") == id_tienda]
        if de_tienda:
            for c in de_tienda:
                if c.get("es_principal"):
                    return c
            return de_tienda[0]
    for c in centros:
        if c.get("es_principal"):
            return c
    return centros[0]


def crear_centro(id_empresa=None, **campos) -> str | None:
    id_empresa = id_empresa or empresa_actual_id()
    nuevo_id = str(uuid.uuid4())
    datos = {k: v for k, v in campos.items() if k in _PERMITIDOS}
    es_principal = 1 if datos.get("es_principal") else 0
    datos.pop("es_principal", None)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM centros_trabajo WHERE id_empresa=%s AND estado='activo'",
                (id_empresa,),
            )
            row = cur.fetchone()
            total = (row[0] if not isinstance(row, dict) else list(row.values())[0]) or 0
            if total == 0:
                es_principal = 1
            if es_principal:
                cur.execute(
                    "UPDATE centros_trabajo SET es_principal=0 WHERE id_empresa=%s",
                    (id_empresa,),
                )
            codigo = _siguiente_codigo(cur, id_empresa)
            cols = ["id_centro", "id_empresa", "codigo_centro", "es_principal", *datos.keys()]
            vals = [nuevo_id, id_empresa, codigo, es_principal, *datos.values()]
            ph = ", ".join(["%s"] * len(cols))
            cur.execute(
                f"INSERT INTO centros_trabajo ({', '.join(cols)}) VALUES ({ph})", vals
            )
            conn.commit()
        return nuevo_id
    except Exception as e:
        logger.error("Error crear_centro: %s", e)
        return None


def actualizar_centro(id_centro, **campos) -> bool:
    datos = {k: v for k, v in campos.items() if k in _PERMITIDOS and k != "es_principal"}
    if not datos:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            asign = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(
                f"UPDATE centros_trabajo SET {asign} WHERE id_centro=%s",
                [*datos.values(), id_centro],
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error actualizar_centro(%s): %s", id_centro, e)
        return False


def marcar_principal(id_centro, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE centros_trabajo SET es_principal=0 WHERE id_empresa=%s",
                (id_empresa,),
            )
            cur.execute(
                "UPDATE centros_trabajo SET es_principal=1 WHERE id_centro=%s",
                (id_centro,),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error marcar_principal(%s): %s", id_centro, e)
        return False


def baja_centro(id_centro) -> bool:
    """Baja lógica (mantiene histórico)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE centros_trabajo SET estado='baja', es_principal=0 WHERE id_centro=%s",
                (id_centro,),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error baja_centro(%s): %s", id_centro, e)
        return False
