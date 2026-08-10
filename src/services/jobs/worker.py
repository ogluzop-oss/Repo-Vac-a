"""
Worker de JOBS (Fase 10) — ejecuta jobs REUTILIZANDO los servicios existentes (NO un segundo motor de IA).
Separa el cómputo pesado (Prophet: forecasting/retraining/degradación) del request HTTP. Aislamiento estricto:
cada job se ejecuta EXCLUSIVAMENTE en el contexto de su `id_empresa`; nunca en otro tenant. Audita
creación/ejecución/fin/error y, al terminar, emite un evento que llega por SSE a la UI.
"""

import logging
import os
import time

from src.services.jobs import idempotencia as _IDEMP
from src.services.jobs.base import JobErrorPermanente, JobErrorTemporal

logger = logging.getLogger("jobs.worker")

# Tipos soportados → función del servicio real correspondiente.
TIPOS = ("prediccion.forecast", "prediccion.retrain", "prediccion.degradacion")


def _max_intentos() -> int:
    # Alineable con SQS_MAX_RECEIVE_COUNT; por defecto 5.
    return int(os.getenv("JOB_MAX_ATTEMPTS", os.getenv("SQS_MAX_RECEIVE_COUNT", "5")))


def procesar(job) -> dict:
    """Ejecuta UN job de forma IDEMPOTENTE y tenant-aislada. Ante reentrega (SQS at-least-once):
      - si el job ya está COMPLETADO → NO se re-ejecuta (JOB_DUPLICATE_IGNORED).
      - error PERMANENTE (validación/tenant) → FALLIDO (a DLQ; no reintentar).
      - error TEMPORAL → se re-lanza para que la cola reentregue, hasta `JOB_MAX_ATTEMPTS` → DLQ.
    Devuelve el resultado (o marcador de duplicado/fallo). No corrompe estado entre tenants."""
    # Idempotencia ATÓMICA (multi-worker seguro): sólo un worker reclama la ejecución. Si ya está COMPLETADO
    # o lo procesa otro worker → no re-ejecuta (evita forecast/modelo duplicados).
    reclamo = _IDEMP.reclamar(job.id, id_empresa=job.id_empresa)
    if reclamo in ("duplicate", "en_curso"):
        _auditar(job, "JOB_DUPLICATE_IGNORED")
        return {"ok": True, "duplicado": True, "motivo": reclamo, "job_id": job.id}

    job.attempt = int(getattr(job, "attempt", 0)) + 1
    job.estado = "EN_CURSO"
    t0 = time.time()
    _auditar(job, "JOB_INICIADO" if job.attempt == 1 else "JOB_RETRIED")
    try:
        res = _despachar(job)
        job.estado = "COMPLETADO"
        job.resultado = res
        _IDEMP.marcar(job.id, _IDEMP.COMPLETADO)
        _auditar(job, "JOB_COMPLETADO")
        _emitir(job, ok=True, duracion=time.time() - t0)
        return res
    except JobErrorPermanente as e:
        job.estado = "FALLIDO"
        job.error = str(e)
        _IDEMP.marcar(job.id, _IDEMP.FALLIDO)
        logger.error("job %s (%s) error PERMANENTE: %s", job.id, job.tipo, e)
        _auditar(job, "JOB_FAILED")
        _emitir(job, ok=False, duracion=time.time() - t0)
        return {"ok": False, "error": str(e), "permanente": True}
    except JobErrorTemporal as e:
        # No marca COMPLETADO: la cola reentregará. Si se agotan intentos → DLQ (FALLIDO permanente).
        if job.attempt >= _max_intentos():
            job.estado = "FALLIDO"
            job.error = f"agotados {job.attempt} intentos: {e}"
            _IDEMP.marcar(job.id, _IDEMP.FALLIDO)
            _auditar(job, "JOB_FAILED")
            _emitir(job, ok=False, duracion=time.time() - t0)
            return {"ok": False, "error": str(e), "dlq": True}
        _IDEMP.marcar(job.id, _IDEMP.PENDIENTE)      # permite reintento controlado
        _auditar(job, "JOB_RETRIED")
        raise                                        # la cola (SQS/Local) decide la reentrega
    except Exception as e:
        # Excepción no clasificada → se trata como PERMANENTE (seguro: no reintenta a ciegas).
        job.estado = "FALLIDO"
        job.error = str(e)
        _IDEMP.marcar(job.id, _IDEMP.FALLIDO)
        logger.error("job %s (%s) falló (no clasificado): %s", job.id, job.tipo, e)
        _auditar(job, "JOB_FAILED")
        _emitir(job, ok=False, duracion=time.time() - t0)
        return {"ok": False, "error": str(e)}


def _despachar(job) -> dict:
    if job.tipo == "prediccion.forecast":
        return _forecast(job)
    if job.tipo == "prediccion.retrain":
        return _retrain(job)
    if job.tipo == "prediccion.degradacion":
        return _degradacion(job)
    raise JobErrorPermanente(f"tipo de job no soportado: {job.tipo}")


def _forecast(job) -> dict:
    from src.services.prediccion import forecasting
    h = int(job.payload.get("horizonte", 30))
    # emitir=False: el evento de UI lo emite el worker al terminar (una sola señal, con correlation_id).
    return forecasting.predecir_ventas(job.id_empresa, horizonte=h, emitir=False)


def _retrain(job) -> dict:
    from src.services.prediccion import retraining
    return retraining.retrain(job.id_empresa, wape_reciente=job.payload.get("wape_reciente"),
                              usuario=job.usuario_origen or "worker")


def _degradacion(job) -> dict:
    from src.services.prediccion import modelos
    return modelos.evaluar_degradacion(job.id_empresa, job.payload.get("entidad", "ventas"),
                                       job.payload.get("wape_reciente"))


def _auditar(job, evento):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("jobs", evento, "jobs",
                      f"{job.id} {job.tipo} emp={job.id_empresa} corr={job.correlation_id}")
    except Exception as e:
        logger.debug("auditar %s: %s", evento, e)


def _emitir(job, *, ok, duracion):
    """Emite el resultado por el Event Bus existente → SSE (canal 'prediccion'), aislado por tenant."""
    try:
        from src.services.eventbus import publish
        publish("prediccion.job_finalizado", id_empresa=job.id_empresa,
                payload={"job_id": job.id, "tipo": job.tipo, "ok": ok,
                         "correlation_id": job.correlation_id, "duracion_seg": round(duracion, 3)})
    except Exception as e:
        logger.debug("emitir job_finalizado: %s", e)


def procesar_pendientes(cola, *, maximo=100) -> int:
    """Drena la cola procesando jobs (proceso worker o tick de scheduler). Confirma (borra) el mensaje sólo si
    NO es un error temporal (para permitir la reentrega). Devuelve nº procesados."""
    n = 0
    while n < maximo:
        job = cola.siguiente()
        if job is None:
            break
        try:
            res = procesar(job)
            temporal = job.estado != "COMPLETADO" and not (res or {}).get("permanente") \
                and not (res or {}).get("dlq") and not (res or {}).get("duplicado") and job.error is None
        except JobErrorTemporal:
            temporal = True
        # Confirmar (borrar) salvo error temporal reintetable; en SQS eso deja que la cola reentregue.
        if hasattr(cola, "confirmar") and not temporal:
            cola.confirmar(job)
        elif hasattr(cola, "rechazar") and temporal:
            cola.rechazar(job)
        n += 1
    return n
