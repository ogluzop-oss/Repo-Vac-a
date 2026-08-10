"""
PCD · Sync · Estado de sincronización (Etapa B · Fase B2). Watermark por (empresa, canal) para la
sincronización incremental. Determinista y multiempresa. Posee su BD (patrón de dominio).
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.sync.estado")


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def cursor(canal, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT watermark FROM cd_sync_estado WHERE id_empresa=%s AND canal=%s",
                        (emp, canal))
            r = cur.fetchone()
            if not r:
                return None
            return list(r.values())[0] if isinstance(r, dict) else r[0]
    except Exception as e:
        logger.error("cursor(%s): %s", canal, e)
        return None


def avanzar(canal, id_empresa=None, *, nuevo_cursor=None, modo="incremental", items=0):
    """Actualiza el watermark y las marcas de sync. Idempotente (upsert por empresa+canal)."""
    emp = _emp(id_empresa)
    col_fecha = "ultimo_full" if modo == "completa" else "ultimo_incremental"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO cd_sync_estado (id_empresa, canal, watermark, {col_fecha}, "
                "items_totales, ts_actualizado) VALUES (%s,%s,%s,%s,%s,%s) "
                f"ON DUPLICATE KEY UPDATE watermark=COALESCE(VALUES(watermark), watermark), "
                f"{col_fecha}=VALUES({col_fecha}), items_totales=items_totales+VALUES(items_totales), "
                "ts_actualizado=VALUES(ts_actualizado)",
                (emp, canal, nuevo_cursor, datetime.now(), int(items or 0), datetime.now()))
            conn.commit()
            return True
    except Exception as e:
        logger.error("avanzar(%s): %s", canal, e)
        return False


def resumen(canal, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT canal, watermark, ultimo_full, ultimo_incremental, items_totales "
                        "FROM cd_sync_estado WHERE id_empresa=%s AND canal=%s", (emp, canal))
            r = cur.fetchone()
            if not r:
                return None
            cols = ("canal", "cursor", "ultimo_full", "ultimo_incremental", "items_totales")
            return r if isinstance(r, dict) else dict(zip(cols, r))
    except Exception as e:
        logger.error("resumen(%s): %s", canal, e)
        return None


__all__ = ["cursor", "avanzar", "resumen"]
