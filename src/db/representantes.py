"""
Capa de datos: REPRESENTANTES LEGALES de la empresa (multi-tenant).

Tabla independiente `representantes_legales` relacionada con `empresas` por
`id_empresa`. Permite varios representantes por empresa, marcar uno como
principal, mantener histórico (estado activo/baja) y elegir el firmante de cada
documento. Forma parte de la fuente única de datos corporativos
([[project_multitenant]]); los documentos lo consumen vía
`empresa.datos_corporativos()`.
"""

import logging
import uuid

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("representantes_db")

_PERMITIDOS = (
    "nombre", "apellidos", "dni_nie", "cargo", "telefono", "email",
    "es_principal", "estado",
)


def listar_representantes(id_empresa=None, solo_activos=True) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = "SELECT * FROM representantes_legales WHERE id_empresa=%s"
            if solo_activos:
                sql += " AND estado='activo'"
            sql += " ORDER BY es_principal DESC, fecha_alta ASC"
            cur.execute(sql, (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_representantes: %s", e)
        return []


def obtener_representante(id_representante) -> dict | None:
    if not id_representante:
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM representantes_legales WHERE id_representante=%s",
                (id_representante,),
            )
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_representante(%s): %s", id_representante, e)
        return None


def representante_principal(id_empresa=None) -> dict | None:
    """Representante marcado como principal (o el primero activo)."""
    id_empresa = id_empresa or empresa_actual_id()
    reps = listar_representantes(id_empresa, solo_activos=True)
    if not reps:
        return None
    for r in reps:
        if r.get("es_principal"):
            return r
    return reps[0]


def crear_representante(id_empresa=None, **campos) -> str | None:
    id_empresa = id_empresa or empresa_actual_id()
    nuevo_id = str(uuid.uuid4())
    datos = {k: v for k, v in campos.items() if k in _PERMITIDOS}
    es_principal = 1 if datos.get("es_principal") else 0
    datos.pop("es_principal", None)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Si no hay ninguno aún, este será principal por defecto.
            cur.execute(
                "SELECT COUNT(*) FROM representantes_legales WHERE id_empresa=%s AND estado='activo'",
                (id_empresa,),
            )
            row = cur.fetchone()
            total = (row[0] if not isinstance(row, dict) else list(row.values())[0]) or 0
            if total == 0:
                es_principal = 1
            if es_principal:
                cur.execute(
                    "UPDATE representantes_legales SET es_principal=0 WHERE id_empresa=%s",
                    (id_empresa,),
                )
            cols = ["id_representante", "id_empresa", "es_principal", *datos.keys()]
            vals = [nuevo_id, id_empresa, es_principal, *datos.values()]
            ph = ", ".join(["%s"] * len(cols))
            cur.execute(
                f"INSERT INTO representantes_legales ({', '.join(cols)}) VALUES ({ph})", vals
            )
            conn.commit()
        return nuevo_id
    except Exception as e:
        logger.error("Error crear_representante: %s", e)
        return None


def actualizar_representante(id_representante, **campos) -> bool:
    datos = {k: v for k, v in campos.items() if k in _PERMITIDOS and k != "es_principal"}
    if not datos:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            asign = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(
                f"UPDATE representantes_legales SET {asign} WHERE id_representante=%s",
                [*datos.values(), id_representante],
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error actualizar_representante(%s): %s", id_representante, e)
        return False


def marcar_principal(id_representante, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE representantes_legales SET es_principal=0 WHERE id_empresa=%s",
                (id_empresa,),
            )
            cur.execute(
                "UPDATE representantes_legales SET es_principal=1 WHERE id_representante=%s",
                (id_representante,),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error marcar_principal(%s): %s", id_representante, e)
        return False


def baja_representante(id_representante) -> bool:
    """Baja lógica (mantiene histórico)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE representantes_legales SET estado='baja', es_principal=0 "
                "WHERE id_representante=%s",
                (id_representante,),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error baja_representante(%s): %s", id_representante, e)
        return False
