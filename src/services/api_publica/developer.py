"""
API Pública · Developer (Fase V · Bloque 3). Gestión de aplicaciones de desarrollador para
integraciones oficiales externas (OAuth2 client credentials). Registra client_id/secret, scopes y
modo sandbox sobre `api_dev_apps`. Multiempresa. El secret se guarda HASHEADO. Servicio (no interfaz):
puede acceder a su propia tabla.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("api_publica.developer")

# Scopes disponibles para terceros (mínimo privilegio; alineados con la REST/GraphQL).
SCOPES_DISPONIBLES = ("read:communications", "write:communications", "read:orders", "write:orders",
                      "read:customers", "read:suppliers", "read:stock", "read:invoices",
                      "read:workflow", "write:workflow", "read:kpis")


def _hash(secret) -> str:
    return hashlib.sha256((secret or "").encode()).hexdigest()


def registrar_app(nombre, *, id_empresa=None, scopes=(), sandbox=True, redirect_uri=None) -> dict:
    """Crea una app de desarrollador. Devuelve client_id + client_secret (el secret solo aquí)."""
    scopes = [s for s in scopes if s in SCOPES_DISPONIBLES]
    client_id = "cid_" + secrets.token_hex(12)
    client_secret = "csec_" + secrets.token_urlsafe(24)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_dev_apps (id_empresa, nombre, client_id, client_secret_hash, "
                "scopes, sandbox, redirect_uri) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, nombre, client_id, _hash(client_secret), ",".join(scopes),
                 1 if sandbox else 0, redirect_uri))
            conn.commit()
        return {"ok": True, "client_id": client_id, "client_secret": client_secret,
                "scopes": scopes, "sandbox": sandbox}
    except Exception as e:
        logger.error("registrar_app: %s", e)
        return {"ok": False, "error": str(e)}


def obtener_app(client_id) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM api_dev_apps WHERE client_id=%s", (client_id,))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception:
        return None


def verificar_credenciales(client_id, client_secret) -> dict | None:
    app = obtener_app(client_id)
    if not app or app.get("estado") != "activa":
        return None
    if app.get("client_secret_hash") != _hash(client_secret):
        return None
    return app


def listar_apps(id_empresa=None) -> list:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, id_empresa, nombre, client_id, scopes, sandbox, estado, creado "
                        "FROM api_dev_apps WHERE (id_empresa=%s OR id_empresa IS NULL) "
                        "ORDER BY creado DESC", (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception:
        return []


def revocar_app(client_id, *, id_empresa=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE api_dev_apps SET estado='revocada' WHERE client_id=%s AND "
                        "(id_empresa=%s OR (%s IS NULL AND id_empresa IS NULL))",
                        (client_id, id_empresa, id_empresa))
            conn.commit()
        return True
    except Exception:
        return False


__all__ = ["SCOPES_DISPONIBLES", "registrar_app", "obtener_app", "verificar_credenciales",
           "listar_apps", "revocar_app"]
