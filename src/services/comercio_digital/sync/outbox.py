"""
PCD · Sync · Outbox (CD-002 · Fase 6). Cola persistente de mensajes SALIENTES (Dominio → Adaptador →
Canal). Idempotente (dedup por (empresa, canal, idempotencia_key)) y con reintentos (backoff). Sin
lógica de proveedor. Posee su BD (patrón de los servicios de dominio); el transporte real es del
adaptador y la orquestación del Sync Engine.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.sync.outbox")

PENDIENTE, ENVIADO, ERROR, DESCARTADO = "PENDIENTE", "ENVIADO", "ERROR", "DESCARTADO"
_BACKOFF_BASE_SEG = 30


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
def _scalar(cur):
    r = cur.fetchone()
    if r is None:
        return None
    return list(r.values())[0] if isinstance(r, dict) else r[0]


def encolar(canal, tipo, payload, *, id_empresa=None, idempotencia_key=None, correlation_id=None,
            communication_id=None, max_intentos=5):
    """Encola un mensaje saliente. IDEMPOTENTE: si ya existe (empresa, canal, idempotencia_key) no se
    duplica; devuelve el id existente. Devuelve el id de la fila (nueva o existente) o None."""
    emp = _emp(id_empresa)
    cuerpo = json.dumps(payload, ensure_ascii=False, default=str) if not isinstance(payload, str) \
        else payload
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if idempotencia_key:
                cur.execute("SELECT id FROM cd_sync_outbox WHERE id_empresa=%s AND canal=%s AND "
                            "idempotencia_key=%s", (emp, canal, idempotencia_key))
                ya = _scalar(cur)
                if ya:
                    return int(ya)          # dedup: no se reencola
            cur.execute(
                "INSERT INTO cd_sync_outbox (id_empresa, canal, tipo, direccion, idempotencia_key, "
                "correlation_id, communication_id, payload, estado, max_intentos, proximo_intento) "
                "VALUES (%s,%s,%s,'push',%s,%s,%s,%s,'PENDIENTE',%s,%s)",
                (emp, canal, tipo, idempotencia_key, correlation_id, communication_id, cuerpo,
                 int(max_intentos), datetime.now()))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("encolar(%s/%s): %s", canal, tipo, e)
        return None


def pendientes(canal=None, id_empresa=None, limite=100):
    """Mensajes listos para procesar (PENDIENTE y proximo_intento vencido)."""
    emp = _emp(id_empresa)
    filas = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT id, id_empresa, canal, tipo, payload, correlation_id, communication_id, "
                   "intentos, max_intentos FROM cd_sync_outbox WHERE id_empresa=%s AND estado='PENDIENTE' "
                   "AND (proximo_intento IS NULL OR proximo_intento<=%s)")
            params = [emp, datetime.now()]
            if canal:
                sql += " AND canal=%s"
                params.append(canal)
            sql += " ORDER BY id LIMIT %s"
            params.append(int(limite))
            cur.execute(sql, tuple(params))
            cols = ("id", "id_empresa", "canal", "tipo", "payload", "correlation_id",
                    "communication_id", "intentos", "max_intentos")
            for f in cur.fetchall():
                vals = list(f.values()) if isinstance(f, dict) else list(f)
                d = dict(zip(cols, vals))
                try:
                    d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
                except Exception:
                    pass
                filas.append(d)
    except Exception as e:
        logger.error("pendientes: %s", e)
    return filas


def marcar_enviado(id_out):
    return _actualizar(id_out, ENVIADO)


def marcar_error(id_out, error, *, backoff_seg=None):
    """Registra un fallo: incrementa intentos; si se agotan → DESCARTADO, si no → PENDIENTE con backoff."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT intentos, max_intentos FROM cd_sync_outbox WHERE id=%s", (id_out,))
            r = cur.fetchone()
            if not r:
                return False
            vals = list(r.values()) if isinstance(r, dict) else list(r)
            intentos = int(vals[0] or 0) + 1
            maxi = int(vals[1] or 5)
            if intentos >= maxi:
                nuevo, prox = DESCARTADO, None
            else:
                nuevo = PENDIENTE
                espera = backoff_seg if backoff_seg is not None else _BACKOFF_BASE_SEG * (2 ** (intentos - 1))
                prox = datetime.now() + timedelta(seconds=espera)
            cur.execute("UPDATE cd_sync_outbox SET estado=%s, intentos=%s, ultimo_error=%s, "
                        "proximo_intento=%s, ts_actualizado=%s WHERE id=%s",
                        (nuevo, intentos, str(error)[:255], prox, datetime.now(), id_out))
            conn.commit()
            return True
    except Exception as e:
        logger.error("marcar_error(%s): %s", id_out, e)
        return False


def reprocesar(canal=None, id_empresa=None):
    """Recuperación (dead-letter): reencola los mensajes DESCARTADOS → PENDIENTE (intentos a 0). Devuelve
    el nº reprocesado. Reutiliza el Outbox existente; no crea una cola paralela."""
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("UPDATE cd_sync_outbox SET estado='PENDIENTE', intentos=0, proximo_intento=%s, "
                   "ultimo_error=NULL, ts_actualizado=%s WHERE id_empresa=%s AND estado='DESCARTADO'")
            params = [datetime.now(), datetime.now(), emp]
            if canal:
                sql += " AND canal=%s"
                params.append(canal)
            cur.execute(sql, tuple(params))
            conn.commit()
            return cur.rowcount
    except Exception as e:
        logger.error("reprocesar: %s", e)
        return 0


def descartados(canal=None, id_empresa=None, limite=100):
    """Cola de mensajes fallidos (dead-letter) para inspección."""
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT id, canal, tipo, intentos, ultimo_error FROM cd_sync_outbox WHERE "
                   "id_empresa=%s AND estado='DESCARTADO'")
            params = [emp]
            if canal:
                sql += " AND canal=%s"
                params.append(canal)
            sql += " ORDER BY id LIMIT %s"
            params.append(int(limite))
            cur.execute(sql, tuple(params))
            cols = ("id", "canal", "tipo", "intentos", "ultimo_error")
            for f in cur.fetchall():
                out.append(f if isinstance(f, dict) else dict(zip(cols, f)))
    except Exception as e:
        logger.error("descartados: %s", e)
    return out


def _actualizar(id_out, estado):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cd_sync_outbox SET estado=%s, ts_actualizado=%s WHERE id=%s",
                        (estado, datetime.now(), id_out))
            conn.commit()
            return True
    except Exception as e:
        logger.error("_actualizar(%s,%s): %s", id_out, estado, e)
        return False


__all__ = ["PENDIENTE", "ENVIADO", "ERROR", "DESCARTADO", "encolar", "pendientes", "marcar_enviado",
           "marcar_error", "reprocesar", "descartados"]
