"""
Gestión avanzada de sesiones (SEC-5): listar, cerrar una sesión remota y revocar todas.
Reutiliza db/sesiones (refresh revocable por jti). Auditado.
"""

import logging
from src.db.conexion import obtener_conexion

logger = logging.getLogger("seguridad.sesiones")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def listar_sesiones(id_usuario) -> list:
    """Sesiones (refresh) activas del usuario."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT jti, id_empresa, expira, creada FROM sesiones WHERE id_usuario=%s "
                        "AND (revocada=0 OR revocada IS NULL) ORDER BY creada DESC", (id_usuario,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.debug("listar_sesiones (esquema variable): %s", e)
        # Fallback tolerante a columnas distintas.
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM sesiones WHERE id_usuario=%s", (id_usuario,))
                return [_fila(cur, r) for r in cur.fetchall()]
        except Exception:
            return []


def cerrar_sesion(jti) -> bool:
    try:
        from src.db import sesiones
        ok = sesiones.revocar(jti)
        _audit("SESION_CERRADA", f"jti={jti}")
        return ok
    except Exception as e:
        logger.error("cerrar_sesion: %s", e)
        return False


def revocar_todas(id_usuario) -> bool:
    try:
        from src.db import sesiones
        ok = sesiones.revocar_usuario(id_usuario)
        _audit("SESIONES_REVOCADAS", f"usuario={id_usuario}")
        return ok
    except Exception as e:
        logger.error("revocar_todas: %s", e)
        return False


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("seguridad", accion, "sesiones", detalle)
    except Exception:
        pass
