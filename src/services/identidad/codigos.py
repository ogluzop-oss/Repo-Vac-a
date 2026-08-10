"""
IOC · Códigos operativos — cada centro puede tener MÚLTIPLES códigos INDEPENDIENTES (visible, interno,
corto, fiscal, contable, logístico, RRHH, TPV, documental, BI, integración). Nunca se reutiliza un
campo para varios propósitos. Multiempresa, auditado.
"""

import logging

from src.services.identidad import _base as B
from src.services.identidad.tipos import valida_tipo_codigo

logger = logging.getLogger("identidad.codigos")


def set_codigo(id_centro, tipo_codigo, valor, *, id_empresa=None) -> bool:
    id_empresa = B.emp(id_empresa)
    tc = valida_tipo_codigo(tipo_codigo)
    if not tc:
        logger.warning("set_codigo: tipo inválido %s", tipo_codigo)
        return False
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ioc_centro_codigos (id_empresa, id_centro, tipo_codigo, valor) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE valor=VALUES(valor), actualizado=NOW()",
                (id_empresa, id_centro, tc, str(valor)[:80]))
            conn.commit()
        B.audit("CODIGO_SET", "ioc_centro_codigos", f"{id_centro}:{tc}={valor}")
        B.evento("identidad.codigo_asignado", ref_entidad="centros_trabajo", ref_id=id_centro,
                 id_empresa=id_empresa, payload={"tipo_codigo": tc, "valor": valor})
        return True
    except Exception as e:
        logger.error("set_codigo: %s", e)
        return False


def get_codigo(id_centro, tipo_codigo) -> str | None:
    tc = valida_tipo_codigo(tipo_codigo)
    if not tc:
        return None
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT valor FROM ioc_centro_codigos WHERE id_centro=%s AND tipo_codigo=%s",
                        (id_centro, tc))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception as e:
        logger.error("get_codigo: %s", e)
        return None


def codigos_de_centro(id_centro) -> dict:
    """Devuelve {tipo_codigo: valor} de todos los códigos del centro."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT tipo_codigo, valor FROM ioc_centro_codigos WHERE id_centro=%s", (id_centro,))
            return {r["tipo_codigo"]: r["valor"] for r in B.filas(cur)}
    except Exception as e:
        logger.error("codigos_de_centro: %s", e)
        return {}


def buscar_por_codigo(tipo_codigo, valor, *, id_empresa=None) -> str | None:
    """Resuelve el id_centro a partir de un código operativo (p.ej. TPV/logístico)."""
    id_empresa = B.emp(id_empresa)
    tc = valida_tipo_codigo(tipo_codigo)
    if not tc:
        return None
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_centro FROM ioc_centro_codigos WHERE id_empresa=%s AND tipo_codigo=%s "
                        "AND valor=%s LIMIT 1", (id_empresa, tc, str(valor)))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception as e:
        logger.error("buscar_por_codigo: %s", e)
        return None
