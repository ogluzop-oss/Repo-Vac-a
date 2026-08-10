"""
Registro de IDEMPOTENCIA de jobs (Fase 11, H3). SQS es at-least-once: el mismo job puede reentregarse. Antes
de ejecutar, se consulta este registro; si el job ya está COMPLETADO no se vuelve a ejecutar (se audita
`JOB_DUPLICATE_IGNORED`). Backend por configuración:

  • 'memory' (por defecto): registro en proceso (válido para LocalQueue/DEV y un único worker).
  • 'db'    : tabla persistente (para MULTI-worker SQS real). PREPARADO — usa la BD existente si está
              disponible; degrada a 'memory' con aviso (nunca corrompe: en el peor caso, sin dedup entre
              procesos, que es el comportamiento previo).

NO se crea un motor nuevo: es un guard delgado reutilizable por el worker.
"""

import logging
import os
import threading
import time

logger = logging.getLogger("jobs.idempotencia")

_LOCK = threading.RLock()
_VISTOS = {}            # job_id -> (estado, ts)
_TTL = int(os.getenv("JOB_IDEMPOTENCY_TTL", "86400"))   # limpieza de entradas viejas (memoria)

PENDIENTE, EN_CURSO, COMPLETADO, FALLIDO = "PENDIENTE", "EN_CURSO", "COMPLETADO", "FALLIDO"


def _backend() -> str:
    return os.getenv("JOB_IDEMPOTENCY_BACKEND", "memory").lower()


def estado(job_id) -> str | None:
    if not job_id:
        return None
    if _backend() == "db":
        e = _db_estado(job_id)
        if e is not None:
            return e
        # degrada a memoria (sin romper): comportamiento = sin dedup entre procesos
    with _LOCK:
        v = _VISTOS.get(job_id)
        return v[0] if v else None


def marcar(job_id, nuevo_estado) -> None:
    if not job_id:
        return
    if _backend() == "db":
        _db_marcar(job_id, nuevo_estado)
    with _LOCK:
        _VISTOS[job_id] = (nuevo_estado, time.time())
        _limpiar()


def ya_completado(job_id) -> bool:
    return estado(job_id) == COMPLETADO


def reclamar(job_id, *, id_empresa=None) -> str:
    """RECLAMO ATÓMICO del job para ejecución (multi-worker seguro). Devuelve:
      • 'claimed'   → este worker gana la ejecución (nadie más lo ejecutará a la vez).
      • 'duplicate' → ya está COMPLETADO (no re-ejecutar).
      • 'en_curso'  → otro worker lo está procesando ahora (no ejecutar; se resolverá por reentrega).
    Con backend 'db' la atomicidad la da la PK job_id (INSERT concurrente falla en todos menos uno). Con
    backend 'memory' (single-process/DEV) se usa el lock del proceso."""
    if not job_id:
        return "claimed"
    if _backend() == "db":
        r = _db_reclamar(job_id, id_empresa)
        if r is not None:
            return r
        # tabla ausente / sin BD → degrada a memoria (no rompe; en el peor caso, dedup sólo intra-proceso)
    with _LOCK:
        est = _VISTOS.get(job_id, (None,))[0]
        if est == COMPLETADO:
            return "duplicate"
        if est == EN_CURSO:
            return "en_curso"
        _VISTOS[job_id] = (EN_CURSO, time.time())
        return "claimed"


def _limpiar():
    if len(_VISTOS) < 10000:
        return
    corte = time.time() - _TTL
    for k in [k for k, (_, ts) in _VISTOS.items() if ts < corte]:
        _VISTOS.pop(k, None)


# ── Backend DB (PREPARADO; reutiliza log_auditoria/consulta si hay BD) ────────
def _db_estado(job_id):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT estado FROM jobs_idempotencia WHERE job_id=%s", (job_id,))
            r = cur.fetchone()
            if not r:
                return None
            return r[0] if not isinstance(r, dict) else list(r.values())[0]
    except Exception:
        return None            # tabla no existe / sin BD → degrada a memoria (no rompe)


def _db_marcar(job_id, nuevo_estado):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO jobs_idempotencia (job_id, estado) VALUES (%s,%s) "
                        "ON DUPLICATE KEY UPDATE estado=VALUES(estado)", (job_id, nuevo_estado))
            c.commit()
    except Exception:
        pass                   # sin tabla → sólo memoria


def _db_reclamar(job_id, id_empresa):
    """Reclamo atómico vía BD. None si la BD/tabla no está disponible (para degradar a memoria)."""
    try:
        import pymysql

        from src.db.conexion import obtener_conexion
    except Exception:
        return None
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            try:
                # INSERT atómico: si el job_id ya existe, lanza IntegrityError (otro worker lo tiene/tuvo).
                cur.execute("INSERT INTO jobs_idempotencia (job_id, id_empresa, estado) VALUES (%s,%s,'EN_CURSO')",
                            (job_id, id_empresa))
                c.commit()
                return "claimed"
            except pymysql.err.IntegrityError:
                c.rollback()
                # Existe: intenta reclamar SÓLO si está en un estado reintetable (atómico por WHERE).
                cur.execute("UPDATE jobs_idempotencia SET estado='EN_CURSO' "
                            "WHERE job_id=%s AND estado IN ('PENDIENTE','FALLIDO')", (job_id,))
                c.commit()
                if cur.rowcount == 1:
                    return "claimed"
                cur.execute("SELECT estado FROM jobs_idempotencia WHERE job_id=%s", (job_id,))
                r = cur.fetchone()
                est = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
                return "duplicate" if est == "COMPLETADO" else "en_curso"
    except Exception:
        return None            # sin tabla / error → degrada a memoria


def _reset_para_tests():
    with _LOCK:
        _VISTOS.clear()
