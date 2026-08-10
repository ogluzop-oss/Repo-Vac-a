"""
Jobs asíncronos (Fase 10). Fachada + factory por `JOB_QUEUE_BACKEND` (local por defecto; sqs preparado).
Helpers para encolar jobs de IA con contexto de tenant. La app usa SIEMPRE `obtener_cola()`; el worker
(`worker.procesar`) reutiliza los servicios de predicción existentes.
"""

import logging
import os

from src.services.jobs.base import Job, JobQueue

logger = logging.getLogger("jobs")

_COLA = None
_BACKEND = None


def backend_configurado() -> str:
    return os.getenv("JOB_QUEUE_BACKEND", "local").lower()


def obtener_cola() -> JobQueue:
    global _COLA, _BACKEND
    b = backend_configurado()
    if _COLA is not None and _BACKEND == b:
        return _COLA
    if b == "sqs":
        from src.services.jobs.sqs import SQSQueue
        _COLA = SQSQueue()                    # falla explícito sin boto3/cola (no fallback silencioso)
    elif b == "local":
        from src.services.jobs.local import LocalQueue
        _COLA = LocalQueue()
    else:
        raise ValueError(f"JOB_QUEUE_BACKEND desconocido: {b!r}")
    _BACKEND = b
    logger.info("job queue backend = %s", _COLA.nombre)
    return _COLA


def encolar_prediccion(id_empresa, *, horizonte=30, usuario=None, correlation_id=None) -> str:
    """Encola un forecast como job (para no bloquear el request). Devuelve el job_id."""
    job = Job(id_empresa, "prediccion.forecast", payload={"horizonte": horizonte},
              usuario_origen=usuario, correlation_id=correlation_id)
    _auditar_creacion(job)
    return obtener_cola().encolar(job)


def encolar_retrain(id_empresa, *, wape_reciente=None, usuario=None) -> str:
    job = Job(id_empresa, "prediccion.retrain", payload={"wape_reciente": wape_reciente}, usuario_origen=usuario)
    _auditar_creacion(job)
    return obtener_cola().encolar(job)


def _auditar_creacion(job):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("jobs", "JOB_CREADO", "jobs", f"{job.id} {job.tipo} emp={job.id_empresa}")
    except Exception as e:
        logger.debug("auditar creacion: %s", e)


def _reset_para_tests():
    global _COLA, _BACKEND
    _COLA = None
    _BACKEND = None
    try:
        from src.services.jobs import idempotencia
        idempotencia._reset_para_tests()
    except Exception:
        pass


__all__ = ["obtener_cola", "encolar_prediccion", "encolar_retrain", "backend_configurado",
           "Job", "JobQueue", "_reset_para_tests"]
