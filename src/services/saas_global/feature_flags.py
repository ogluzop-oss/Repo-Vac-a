"""
Global SaaS · Feature Flags Cloud (Fase VI · Bloque 13). Flags evaluables por ÁMBITO jerárquico:
usuario > empresa > plan > región > global (el más específico gana). Sobre `cloud_feature_flags`.
Permite activar funcionalidades por región/empresa/plan/usuario sin desplegar código nuevo.
Multiempresa/multi-región.
"""

from __future__ import annotations

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("saas_global.flags")

AMBITOS = ("global", "region", "empresa", "plan", "usuario")
# Precedencia: el más específico primero.
_PRECEDENCIA = ("usuario", "empresa", "plan", "region", "global")


def fijar(flag, activo, *, ambito="global", ambito_id=None) -> bool:
    if ambito not in AMBITOS:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cloud_feature_flags (flag, ambito, ambito_id, activo) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE activo=VALUES(activo), "
                        "actualizado=NOW()", (flag, ambito, ambito_id, 1 if activo else 0))
            conn.commit()
        return True
    except Exception as e:
        logger.error("fijar flag: %s", e)
        return False


def _valor(flag, ambito, ambito_id):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT activo FROM cloud_feature_flags WHERE flag=%s AND ambito=%s AND "
                        "(ambito_id=%s OR (%s IS NULL AND ambito_id IS NULL))",
                        (flag, ambito, ambito_id, ambito_id))
            r = cur.fetchone()
        if r is not None:
            return bool(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception:
        pass
    return None


def activo(flag, *, id_usuario=None, id_empresa=None, plan=None, region=None,
           por_defecto=False) -> bool:
    """Evalúa un flag resolviendo del ámbito MÁS específico al global."""
    ensure_schema()
    ambito_id = {"usuario": id_usuario, "empresa": id_empresa, "plan": plan, "region": region,
                 "global": None}
    for ambito in _PRECEDENCIA:
        if ambito != "global" and ambito_id[ambito] is None:
            continue
        v = _valor(flag, ambito, ambito_id[ambito])
        if v is not None:
            return v
    return por_defecto


def listar(flag=None) -> list:
    q = "SELECT flag, ambito, ambito_id, activo FROM cloud_feature_flags"
    p = ()
    if flag:
        q += " WHERE flag=%s"; p = (flag,)
    try:
        ensure_schema()
        from src.db.conexion import _filas_a_dicts
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        return []


__all__ = ["AMBITOS", "fijar", "activo", "listar"]
