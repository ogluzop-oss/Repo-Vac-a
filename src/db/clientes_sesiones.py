"""
Sesión del CLIENTE final del storefront (Generador de Apps Móviles PWA, Fase 2) — tabla
`cd_clientes_sesiones` (migr. 0301). Token opaco DB-backed (revocable), distinto del carrito
anónimo (`cd_carrito_lineas`, sin identidad) y del JWT de empleado (`seguridad.tokens`, stateless).
"""

import logging
import secrets
from datetime import datetime, timedelta

from src.db.conexion import obtener_conexion

logger = logging.getLogger("clientes_sesiones.db")

DIAS_SESION_DEFECTO = 30


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear_sesion(id_empresa, id_cliente, *, dias=DIAS_SESION_DEFECTO) -> str | None:
    """Alta de una sesión nueva (tras Magic Link o WebAuthn confirmados) — token aleatorio de 32
    bytes (64 hex), imposible de adivinar. None si la escritura falla (degradación honesta: nunca
    se finge una sesión que no quedó persistida)."""
    token = secrets.token_hex(32)
    expira = datetime.now() + timedelta(days=dias)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_clientes_sesiones (token, id_empresa, id_cliente, expira) "
                "VALUES (%s,%s,%s,%s)", (token, id_empresa, id_cliente, expira))
            conn.commit()
        return token
    except Exception as e:
        logger.error("crear_sesion(%s,%s): %s", id_empresa, id_cliente, e)
        return None


def resolver_sesion(token) -> dict | None:
    """Sesión vigente para `token`, o None si no existe/caducó (y la borra de paso — limpieza
    perezosa, sin necesidad de un job aparte). Toca `ultima_actividad` en cada resolución."""
    if not token:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cd_clientes_sesiones WHERE token=%s", (token,))
            fila = cur.fetchone()
            if not fila:
                return None
            fila = _fila(cur, fila)
            if fila["expira"] < datetime.now():
                cur.execute("DELETE FROM cd_clientes_sesiones WHERE token=%s", (token,))
                conn.commit()
                return None
            cur.execute("UPDATE cd_clientes_sesiones SET ultima_actividad=NOW() WHERE token=%s",
                        (token,))
            conn.commit()
            return fila
    except Exception as e:
        logger.error("resolver_sesion: %s", e)
        return None


def cerrar_sesion(token) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_clientes_sesiones WHERE token=%s", (token,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("cerrar_sesion: %s", e)
        return False


def purgar_expiradas() -> int:
    """Barrido de limpieza (opcional, job periódico): borra sesiones ya caducadas que nadie volvió
    a usar (la limpieza perezosa de `resolver_sesion` solo cubre las que SÍ se vuelven a intentar
    usar)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_clientes_sesiones WHERE expira < NOW()")
            n = cur.rowcount
            conn.commit()
        return n
    except Exception as e:
        logger.error("purgar_expiradas: %s", e)
        return 0
