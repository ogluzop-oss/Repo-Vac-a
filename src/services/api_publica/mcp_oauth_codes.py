"""
Códigos de autorización OAuth 2.1/PKCE del conector MCP (migr. 0283, tabla `mcp_oauth_codes`).

Pieza nueva y pequeña del flujo `src/mcp_server/oauth.py`: el CLIENTE (client_id/secret/
redirect_uri) vive en `api_dev_apps` (reutilizada, ver `developer.py`); esto es solo el enlace
efímero y de un solo uso entre "un usuario real se autenticó" y "un cliente MCP puede canjear
ese hecho por un JWT" — no existía nada parecido en el sistema porque hasta ahora NINGÚN flujo
de auth usaba authorization code + PKCE (el login API es directo usuario+contraseña → JWT).

El código en claro solo se devuelve una vez al cliente (en la redirección); en reposo se
guarda HASHEADO (mismo criterio que `client_secret_hash`/refresh tokens hasheados en `sesiones`).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import secrets

from src.db.conexion import obtener_conexion

logger = logging.getLogger("api_publica.mcp_oauth_codes")

TTL_MINUTOS = 5


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _ensure_schema():
    """Crea la tabla si la migración 0283 todavía no se aplicó en esta BD (degradable, mismo
    patrón que el resto de `services/api_publica/*`)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mcp_oauth_codes (
                    id                     BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    code_hash              VARCHAR(128) NOT NULL,
                    client_id              VARCHAR(48)  NOT NULL,
                    id_usuario             BIGINT       NOT NULL,
                    id_empresa             CHAR(36)              DEFAULT NULL,
                    redirect_uri           VARCHAR(500) NOT NULL,
                    code_challenge         VARCHAR(128) NOT NULL,
                    code_challenge_method  VARCHAR(10)  NOT NULL DEFAULT 'S256',
                    scope                  VARCHAR(255)          DEFAULT NULL,
                    amr                    VARCHAR(32)           DEFAULT NULL,
                    creado                 DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expira                 DATETIME     NOT NULL,
                    usado                  TINYINT      NOT NULL DEFAULT 0,
                    UNIQUE KEY uq_mcp_code_hash (code_hash),
                    INDEX idx_mcp_code_client (client_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            conn.commit()
    except Exception as e:
        logger.debug("_ensure_schema mcp_oauth_codes: %s", e)


def crear_codigo(*, client_id, id_usuario, id_empresa, redirect_uri, code_challenge,
                 code_challenge_method="S256", scope=None, amr=None) -> str:
    """Genera y persiste (hasheado) un código de un solo uso. Devuelve el código EN CLARO
    (única vez que existe fuera de la BD, igual que `developer.registrar_app` con el secret)."""
    _ensure_schema()
    codigo = secrets.token_urlsafe(32)
    expira = _dt.datetime.now() + _dt.timedelta(minutes=TTL_MINUTOS)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO mcp_oauth_codes (code_hash, client_id, id_usuario, id_empresa, "
            "redirect_uri, code_challenge, code_challenge_method, scope, amr, expira) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (_hash(codigo), client_id, id_usuario, id_empresa, redirect_uri, code_challenge,
             code_challenge_method, scope, amr, expira))
        conn.commit()
    return codigo


def consumir_codigo(codigo: str, *, client_id: str, redirect_uri: str) -> dict | None:
    """Valida y marca usado un código (de un solo uso, atómico vía `usado=0` en el WHERE).
    Devuelve sus datos o `None` si no existe/ya se usó/caducó/no coincide client_id+redirect_uri.

    FAIL-CLOSED a propósito: el código se marca `usado=1` en ESTE intento con independencia de si
    el llamador luego supera o no la comprobación PKCE (eso lo hace `mcp_server/oauth.py` después,
    con los datos que devolvemos). Un cliente legítimo nunca manda un `code_verifier` incorrecto
    (lo calculó él mismo), así que esto nunca afecta al flujo normal; lo que impide es que alguien
    con un código robado (p. ej. interceptado en la redirección) pueda PROBAR varios verifiers
    contra el mismo código — el primer intento, acierte o no, lo quema."""
    _ensure_schema()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, id_usuario, id_empresa, redirect_uri, code_challenge, "
                "code_challenge_method, scope, amr, expira, usado FROM mcp_oauth_codes "
                "WHERE code_hash=%s AND client_id=%s", (_hash(codigo), client_id))
            fila = cur.fetchone()
            if not fila:
                return None
            d = (fila if isinstance(fila, dict) else
                 dict(zip([c[0] for c in cur.description], fila)))
            if int(d.get("usado") or 0):
                logger.warning("Intento de reutilizar un código de autorización MCP (client=%s)",
                               client_id)
                return None
            expira = d.get("expira")
            if expira and expira < _dt.datetime.now():
                return None
            if d.get("redirect_uri") != redirect_uri:
                return None
            # Marca consumido ANTES de devolver (de un solo uso incluso ante llamadas concurrentes).
            cur.execute("UPDATE mcp_oauth_codes SET usado=1 WHERE id=%s AND usado=0", (d["id"],))
            conn.commit()
            if cur.rowcount != 1:
                return None   # otra petición concurrente ganó la carrera
            return d
    except Exception as e:
        logger.error("consumir_codigo: %s", e)
        return None


__all__ = ["TTL_MINUTOS", "crear_codigo", "consumir_codigo"]
