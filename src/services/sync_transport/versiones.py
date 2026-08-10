"""
Control de versiones por terminal (Fase 4, SUBFASE 4.7). Cada terminal conoce su version de
software, version de BD (ultima migracion), ultima sincronizacion, ultimo paquete, revision y
hash. Base para la deteccion de inconsistencias (4.11) y el actualizador (4.8).
"""

import logging

logger = logging.getLogger("sync_transport.versiones")

VERSION_SW = "2.4.0"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def version_sw_actual() -> str:
    return VERSION_SW


def version_db_actual() -> str:
    try:
        from src.database.migraciones import MODULOS
        return MODULOS[-1].split("_")[0] if MODULOS else "0000"
    except Exception:
        return "0000"


def obtener(id_empresa, id_tienda) -> dict | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM terminal_versiones WHERE id_empresa=%s AND id_tienda=%s",
                        (emp, int(id_tienda or 0)))
            r = _filas_a_dicts(cur, cur.fetchall())
            return r[0] if r else None
    except Exception as e:
        logger.error("obtener version: %s", e)
        return None


def actualizar(id_empresa, id_tienda, *, ultimo_paquete=None, hash=None,
               version_sw=None, version_db=None) -> bool:
    emp = _emp(id_empresa)
    vsw = version_sw or version_sw_actual()
    vdb = version_db or version_db_actual()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO terminal_versiones (id_empresa, id_tienda, version_sw, version_db, "
                "ultima_sync, ultimo_paquete, revision, hash) VALUES (%s,%s,%s,%s,NOW(),%s,1,%s) "
                "ON DUPLICATE KEY UPDATE version_sw=VALUES(version_sw), version_db=VALUES(version_db), "
                "ultima_sync=NOW(), ultimo_paquete=COALESCE(VALUES(ultimo_paquete),ultimo_paquete), "
                "revision=revision+1, hash=COALESCE(VALUES(hash),hash)",
                (emp, int(id_tienda or 0), vsw, vdb, ultimo_paquete, hash))
            c.commit()
        return True
    except Exception as e:
        logger.error("actualizar version: %s", e)
        return False
