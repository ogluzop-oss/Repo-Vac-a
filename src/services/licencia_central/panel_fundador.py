"""
Cuenta y sesiones del PANEL WEB DEL FUNDADOR (Fase 4). UNA sola cuenta, sin relación con la tabla
`usuarios` de ningún cliente ni con `src.seguridad.tokens` (JWT) — reutiliza el mismo hash de
contraseña (`src.seguridad.passwords`, Argon2id) y el mismo patrón de sesión-en-BD sin `secret_key`
que `services.compras.b2b_sesion_empresa`/`services.compras.proveedor_sesion` (token opaco +
expiración), aquí entregado vía cookie HttpOnly en vez de la URL.

`crear_cuenta` se niega a crear una segunda cuenta a propósito: es un panel de una sola persona.
"""

import logging
import secrets
from datetime import datetime, timedelta

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("licencia_central.panel_fundador")

MINUTOS_SESION = 480


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def existe_cuenta() -> bool:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM panel_fundador_admin")
            row = _fila(cur, cur.fetchone())
            return int(row["n"]) > 0
    except Exception as e:
        logger.error("existe_cuenta: %s", e)
        return False


def crear_cuenta(usuario: str, password: str) -> dict:
    """Crea la ÚNICA cuenta del panel. Se niega si ya existe una (usa el panel para todo lo
    demás; si necesitas cambiar la contraseña, hazlo desde el propio panel, no re-ejecutando esto)."""
    usuario = (usuario or "").strip()
    if not usuario or not password:
        return {"ok": False, "error": "Faltan datos."}
    if existe_cuenta():
        return {"ok": False, "error": "Ya existe una cuenta del panel del fundador."}
    from src.seguridad import politica
    ok_pol, motivo = politica.validar(password)
    if not ok_pol:
        return {"ok": False, "error": motivo}
    from src.seguridad.passwords import hash_password
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO panel_fundador_admin (usuario, password_hash) VALUES (%s,%s)",
                (usuario, hash_password(password)))
            conn.commit()
        logger.info("Cuenta del panel del fundador creada: %s", usuario)
        return {"ok": True}
    except Exception as e:
        logger.error("crear_cuenta: %s", e)
        return {"ok": False, "error": "Error interno."}


def verificar_password(usuario: str, password: str) -> bool:
    if not usuario or not password:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM panel_fundador_admin WHERE usuario=%s", (usuario,))
            row = cur.fetchone()
            if not row:
                return False
            hash_almacenado = row[0] if not isinstance(row, dict) else row["password_hash"]
        from src.seguridad.passwords import verificar
        ok, _hash_nuevo = verificar(password, hash_almacenado)
        return bool(ok)
    except Exception as e:
        logger.error("verificar_password: %s", e)
        return False


def registrar_acceso(usuario: str) -> None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE panel_fundador_admin SET ultimo_acceso=NOW() WHERE usuario=%s", (usuario,))
            conn.commit()
    except Exception as e:
        logger.error("registrar_acceso: %s", e)


def crear_sesion(usuario: str, *, minutos: int = MINUTOS_SESION) -> dict:
    token = secrets.token_urlsafe(32)
    expira = datetime.now() + timedelta(minutes=minutos)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO panel_fundador_sesiones (token_sesion, usuario, expira) VALUES (%s,%s,%s)",
                (token, usuario, expira))
            conn.commit()
        return {"ok": True, "token": token, "expira": expira.isoformat()}
    except Exception as e:
        logger.error("crear_sesion: %s", e)
        return {"ok": False, "error": "Error interno."}


def resolver_sesion(token: str) -> dict | None:
    if not token:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM panel_fundador_sesiones WHERE token_sesion=%s", (token,))
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


def cerrar_sesion(token: str) -> None:
    if not token:
        return
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM panel_fundador_sesiones WHERE token_sesion=%s", (token,))
            conn.commit()
    except Exception as e:
        logger.error("cerrar_sesion: %s", e)
