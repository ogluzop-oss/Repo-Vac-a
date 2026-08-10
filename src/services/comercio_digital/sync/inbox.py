"""
PCD · Sync · Inbox (CD-002 · Fase 6). Deduplicación de mensajes ENTRANTES (pull/webhook) por
(empresa, canal, external_id). NO muta el dominio: solo registra la recepción para dedup y trazas.
Posee su BD (patrón de los servicios de dominio).
"""

from __future__ import annotations

import json
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.sync.inbox")

RECIBIDO, PROCESADO, DESCARTADO = "RECIBIDO", "PROCESADO", "DESCARTADO"


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def visto(canal, external_id, id_empresa=None) -> bool:
    """True si ya se recibió (empresa, canal, external_id) → deduplicación."""
    if not external_id:
        return False
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM cd_sync_inbox WHERE id_empresa=%s AND canal=%s AND "
                        "external_id=%s LIMIT 1", (emp, canal, external_id))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("visto(%s/%s): %s", canal, external_id, e)
        return False


def registrar(canal, external_id, tipo, payload, *, id_empresa=None, correlation_id=None):
    """Registra un mensaje entrante. IDEMPOTENTE: si el external_id ya existe, no duplica (None)."""
    emp = _emp(id_empresa)
    cuerpo = json.dumps(payload, ensure_ascii=False, default=str) if not isinstance(payload, str) \
        else payload
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM cd_sync_inbox WHERE id_empresa=%s AND canal=%s AND "
                        "external_id=%s", (emp, canal, external_id))
            r = cur.fetchone()
            if r:
                return None                 # ya registrado → dedup
            cur.execute(
                "INSERT INTO cd_sync_inbox (id_empresa, canal, external_id, tipo, correlation_id, "
                "payload, estado) VALUES (%s,%s,%s,%s,%s,%s,'RECIBIDO')",
                (emp, canal, external_id, tipo, correlation_id, cuerpo))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("registrar(%s/%s): %s", canal, external_id, e)
        return None


def marcar_procesado(id_in):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_sync_inbox SET estado='PROCESADO' WHERE id=%s", (id_in,))
            conn.commit()
            return True
    except Exception as e:
        logger.error("marcar_procesado(%s): %s", id_in, e)
        return False


__all__ = ["RECIBIDO", "PROCESADO", "DESCARTADO", "visto", "registrar", "marcar_procesado"]
