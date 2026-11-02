"""
Control de sesión única de escritorio (migr 0231): salvo SUPERADMIN, un usuario no puede tener dos
instancias de Smart Manager abiertas a la vez con sus credenciales — así se evita que un mismo operario
quede fichado en dos cajas/equipos simultáneamente. SUPERADMIN queda exento a propósito, para poder
conectarse en paralelo a varias tiendas y supervisarlas de forma remota.

Una sesión se considera "viva" mientras reciba latidos (`actualizar_latido`, llamado periódicamente
desde `main.py` mientras la app está abierta); si el proceso muere sin hacer logout (cierre forzado,
corte de luz…) la fila queda huérfana pero expira sola pasado `TTL_SEG` sin latido, así que el usuario
no queda bloqueado para siempre.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger(__name__)

TTL_SEG = 90


def hay_sesion_activa_otro_equipo(id_usuario: int) -> bool:
    """True si ya existe una sesión viva (latido dentro de TTL_SEG) para este usuario."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM sesiones_desktop_activas WHERE id_usuario=%s "
                    "AND latido_en >= NOW() - INTERVAL %s SECOND",
                    (id_usuario, TTL_SEG),
                )
                row = cur.fetchone()
                total = row[0] if not isinstance(row, dict) else row.get("COUNT(*)", 0)
                return int(total or 0) > 0
    except Exception as e:
        logger.error("hay_sesion_activa_otro_equipo(%s): %s", id_usuario, e)
        return False


def registrar_sesion(id_usuario: int, nombre: str, perfil: str) -> int | None:
    """Crea la fila de sesión activa y devuelve su id (para latido/cierre posteriores)."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sesiones_desktop_activas (id_usuario, nombre, perfil) "
                    "VALUES (%s, %s, %s)",
                    (id_usuario, nombre, perfil),
                )
                conn.commit()
                return cur.lastrowid
    except Exception as e:
        logger.error("registrar_sesion(%s): %s", id_usuario, e)
        return None


def actualizar_latido(id_sesion: int) -> None:
    if not id_sesion:
        return
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sesiones_desktop_activas SET latido_en=NOW() WHERE id=%s",
                    (id_sesion,),
                )
                conn.commit()
    except Exception as e:
        logger.error("actualizar_latido(%s): %s", id_sesion, e)


def cerrar_sesion(id_sesion: int) -> None:
    if not id_sesion:
        return
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sesiones_desktop_activas WHERE id=%s", (id_sesion,))
                conn.commit()
    except Exception as e:
        logger.error("cerrar_sesion(%s): %s", id_sesion, e)
