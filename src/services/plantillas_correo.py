"""
Plantillas de correo (FASE COM-5).

Plantillas por empresa (pedidos/facturas/contratos/nóminas/AEAT/workflow/auditoría) con
variables dinámicas estilo {{variable}}. `render(codigo, contexto)` devuelve (asunto, cuerpo).
"""

import logging
import re

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("plantillas_correo")
TIPOS = ("pedidos", "facturas", "contratos", "nominas", "aeat", "workflow", "auditoria", "general")
_RE_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def crear_plantilla(codigo, asunto, cuerpo, *, tipo="general", id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    if tipo not in TIPOS:
        tipo = "general"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO plantillas_correo (id_empresa, codigo, tipo, asunto, cuerpo) "
                        "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE asunto=VALUES(asunto), "
                        "cuerpo=VALUES(cuerpo), tipo=VALUES(tipo), activo=1",
                        (id_empresa, codigo, tipo, asunto, cuerpo))
            conn.commit()
            cur.execute("SELECT id FROM plantillas_correo WHERE id_empresa=%s AND codigo=%s",
                        (id_empresa, codigo))
            r = cur.fetchone()
            return r[0] if not isinstance(r, dict) else list(r.values())[0]
    except Exception as e:
        logger.error("crear_plantilla: %s", e)
        return None


def _sustituir(texto, contexto):
    return _RE_VAR.sub(lambda m: str(contexto.get(m.group(1), m.group(0))), texto or "")


def render(codigo, contexto=None, id_empresa=None) -> tuple | None:
    """Devuelve (asunto, cuerpo) con las {{variables}} sustituidas, o None si no existe."""
    id_empresa = _emp(id_empresa)
    contexto = contexto or {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT asunto, cuerpo FROM plantillas_correo WHERE id_empresa=%s AND codigo=%s "
                        "AND activo=1", (id_empresa, codigo))
            r = cur.fetchone()
            if not r:
                return None
            d = r if isinstance(r, dict) else dict(zip([x[0] for x in cur.description], r))
        return _sustituir(d["asunto"], contexto), _sustituir(d["cuerpo"], contexto)
    except Exception as e:
        logger.error("render: %s", e)
        return None
