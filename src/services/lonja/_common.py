"""Helpers de la Lonja B2B (conexión, transacción real con bloqueo, auditoría, token)."""

import logging
import secrets

logger = logging.getLogger("lonja")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _tx():
    """Transacción REAL (autocommit off + COMMIT/ROLLBACK) para que `SELECT … FOR UPDATE` mantenga el
    bloqueo durante toda la compra/adjudicación. No llamar a commit() dentro."""
    from src.db.conexion import transaccion
    return transaccion()


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def _uno(cur):
    fs = _filas(cur)
    return fs[0] if fs else None


def _audit(accion, detalle, tabla="lonja_listados"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("lonja", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _token():
    return secrets.token_urlsafe(32)[:64]
