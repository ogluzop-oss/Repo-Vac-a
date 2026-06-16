"""
Persistencia de sesiones / refresh tokens (C1.4 — base para la API REST).

Guarda el refresh token HASHEADO (nunca en claro) junto a su `jti` para poder
revocarlo. La API (A1) usará `registrar` al emitir y `es_valido`/`revocar` al
refrescar o cerrar sesión.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("sesiones_db")


def registrar(id_usuario, jti, refresh_hash, expira=None, id_empresa=None) -> bool:
    id_empresa = id_empresa or EMPRESA_DEFAULT_ID
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sesiones (id_usuario, id_empresa, jti, refresh_hash, expira) "
                "VALUES (%s,%s,%s,%s,%s)",
                (id_usuario, id_empresa, jti, refresh_hash, expira))
            conn.commit()
        return True
    except Exception as e:
        logger.error("registrar sesión: %s", e)
        return False


def es_valido(jti, refresh_hash=None) -> bool:
    """True si la sesión existe, no está revocada ni caducada (y, si se indica,
    el hash del refresh coincide)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT refresh_hash, revocado, expira FROM sesiones WHERE jti=%s", (jti,))
            r = cur.fetchone()
            if not r:
                return False
            rh, revocado, expira = (r if not isinstance(r, dict)
                                    else (r["refresh_hash"], r["revocado"], r["expira"]))
            if revocado:
                return False
            if expira is not None:
                import datetime as _dt
                if expira < _dt.datetime.now():
                    return False
            if refresh_hash is not None and rh != refresh_hash:
                return False
            return True
    except Exception as e:
        logger.error("es_valido sesión: %s", e)
        return False


def revocar(jti) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE sesiones SET revocado=1 WHERE jti=%s", (jti,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("revocar sesión: %s", e)
        return False


def revocar_usuario(id_usuario) -> bool:
    """Revoca todas las sesiones de un usuario (logout global / cambio de contraseña)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE sesiones SET revocado=1 WHERE id_usuario=%s", (id_usuario,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("revocar_usuario: %s", e)
        return False
