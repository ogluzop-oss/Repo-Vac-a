"""
Cola de JOBS asíncronos (Fase 10) — abstracción única para descargar del request HTTP las tareas pesadas
(p. ej. Prophet). NO es un segundo motor: los jobs INVOCAN los servicios existentes (forecasting/retraining).
Todo job lleva SIEMPRE su contexto de tenant y se ejecuta SÓLO en ese tenant (aislamiento estricto).

Backends por configuración `JOB_QUEUE_BACKEND=local|sqs`: LocalQueue (DEV, en proceso) y SQSQueue (PREPARADO,
degradable). Responsabilidades separadas: SQS→jobs; Redis→distribución de eventos SSE; Event Bus→dominio.
"""

import time
import uuid


class Job:
    """Unidad de trabajo con contexto de tenant OBLIGATORIO."""
    __slots__ = ("id", "id_empresa", "tipo", "payload", "usuario_origen", "correlation_id",
                 "created_at", "estado", "resultado", "error", "attempt")

    def __init__(self, id_empresa, tipo, *, payload=None, usuario_origen=None, correlation_id=None):
        if id_empresa is None or str(id_empresa).strip() == "":
            raise ValueError("id_empresa obligatorio en todo Job (aislamiento multi-tenant)")
        self.id = "job_" + uuid.uuid4().hex[:16]
        self.id_empresa = str(id_empresa)
        self.tipo = tipo
        self.payload = payload or {}
        self.usuario_origen = usuario_origen
        self.correlation_id = correlation_id or ("corr_" + uuid.uuid4().hex[:12])
        self.created_at = time.time()
        self.estado = "PENDIENTE"          # PENDIENTE → EN_CURSO → COMPLETADO | FALLIDO
        self.resultado = None
        self.error = None
        self.attempt = 0                   # nº de intento (SQS reentrega → incrementa)

    def to_dict(self) -> dict:
        return {"id": self.id, "id_empresa": self.id_empresa, "tipo": self.tipo, "payload": self.payload,
                "usuario_origen": self.usuario_origen, "correlation_id": self.correlation_id,
                "created_at": self.created_at, "estado": self.estado, "error": self.error,
                "attempt": self.attempt}

    @classmethod
    def from_dict(cls, d):
        j = cls(d["id_empresa"], d["tipo"], payload=d.get("payload"),
                usuario_origen=d.get("usuario_origen"), correlation_id=d.get("correlation_id"))
        j.id = d.get("id", j.id)
        j.created_at = d.get("created_at", j.created_at)
        j.estado = d.get("estado", j.estado)
        j.attempt = int(d.get("attempt", 0))
        return j


class JobError(Exception):
    """Base de errores de job."""


class JobErrorPermanente(JobError):
    """Error que NO se debe reintentar (validación, tenant, payload inválido) → FAILED/DLQ."""


class JobErrorTemporal(JobError):
    """Error transitorio (red, recurso momentáneo) → reintento controlado."""


class JobQueue:
    nombre = "base"

    def encolar(self, job: Job) -> str:
        raise NotImplementedError

    def siguiente(self, *, timeout=0):
        """Devuelve el próximo Job o None."""
        raise NotImplementedError

    def profundidad(self) -> int:
        raise NotImplementedError
