"""
Sesión de la Extranet de Empresa (Smart Suppliers · Fase B). El botón "Entrar al portal B2B" del
escritorio (Fase E) llamará a `crear_sesion` con la empresa/usuario/tienda de la conexión remota
activa EN ESE MOMENTO. Mismo patrón sin-cookies que el Portal Proveedor: el token viaja en la URL y se
revalida en cada petición — sin `secret_key` nuevo en la app Flask compartida.

`id_tienda` queda FIJADO en el token (requisito de negocio confirmado): el portal nunca permite
reponer/comprar para una tienda distinta de la que estaba activa al entrar. Para reabastecer otra
tienda hay que volver a Smart Manager, conectarse a ella y entrar de nuevo al portal.
"""

import logging
import secrets
from datetime import datetime, timedelta

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("compras.b2b_sesion_empresa")

MINUTOS_SESION = 120


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _sector_de_empresa(id_empresa) -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT sector_id FROM empresas WHERE id_empresa=%s", (id_empresa,))
            row = cur.fetchone()
            if not row:
                return None
            return (row[0] if not isinstance(row, dict) else row["sector_id"])
    except Exception as e:
        logger.error("_sector_de_empresa(%s): %s", id_empresa, e)
        return None


def crear_sesion(id_empresa, id_usuario, id_tienda, *, nombre_usuario=None,
                 minutos=MINUTOS_SESION) -> dict:
    """Emite el token de entrada al Portal B2B. Falla explícitamente si la empresa no tiene sector
    asignado (el catálogo B2B no podría filtrarse) o si no hay tienda activa (nada que reponer)."""
    sector_id = _sector_de_empresa(id_empresa)
    if not sector_id:
        return {"ok": False, "error": "empresa_sin_sector_comercial_asignado"}
    if not id_tienda:
        return {"ok": False, "error": "sin_tienda_activa_conectate_a_una_tienda_primero"}
    token = secrets.token_urlsafe(32)
    expira = datetime.now() + timedelta(minutes=minutos)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO b2b_sesiones_empresa (token_sesion, id_empresa, id_usuario, "
                "nombre_usuario, id_tienda, sector_id, expira) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (token, id_empresa, id_usuario, nombre_usuario, id_tienda, sector_id, expira))
            conn.commit()
        return {"ok": True, "token": token, "expira": expira.isoformat()}
    except Exception as e:
        logger.error("crear_sesion(%s): %s", id_empresa, e)
        return {"ok": False, "error": "error_interno"}


def resolver_sesion(token: str) -> dict | None:
    if not token:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM b2b_sesiones_empresa WHERE token_sesion=%s", (token,))
            row = cur.fetchone()
            ses = _fila(cur, row) if row else None
        if not ses:
            return None
        expira = ses.get("expira")
        if expira and isinstance(expira, str):
            expira = datetime.fromisoformat(expira[:19])
        if expira and expira < datetime.now():
            return None
        return ses
    except Exception as e:
        logger.error("resolver_sesion: %s", e)
        return None
