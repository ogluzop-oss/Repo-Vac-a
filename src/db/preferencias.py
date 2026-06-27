"""
Preferencias de usuario (clave/valor) — capa de datos para UX.

Almacen ligero y tolerante a fallos: si la tabla no existe o la BD falla, devuelve el valor
por defecto sin romper la interfaz. No multiempresa (las preferencias son por usuario/persona).
"""

import logging

logger = logging.getLogger("db.preferencias")


def obtener(id_usuario, clave, default=None):
    if not id_usuario:
        return default
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT valor FROM preferencias_usuario WHERE id_usuario=%s AND clave=%s",
                        (id_usuario, clave))
            r = cur.fetchone()
            if not r:
                return default
            return r[0] if not isinstance(r, dict) else r.get("valor")
    except Exception as e:
        logger.debug("obtener(%s,%s): %s", id_usuario, clave, e)
        return default


def guardar(id_usuario, clave, valor) -> bool:
    if not id_usuario:
        return False
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO preferencias_usuario (id_usuario, clave, valor) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE valor=VALUES(valor), actualizado=NOW()",
                (id_usuario, clave, None if valor is None else str(valor)))
            conn.commit()
        return True
    except Exception as e:
        logger.debug("guardar(%s,%s): %s", id_usuario, clave, e)
        return False


def obtener_bool(id_usuario, clave, default=False) -> bool:
    v = obtener(id_usuario, clave, None)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "si", "sí", "on")
