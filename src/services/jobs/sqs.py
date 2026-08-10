"""
Backend SQS de la cola de jobs (Fase 10) — PREPARADO, degradable. `boto3` perezoso: si no está instalado o no
hay cola real, la construcción falla explícitamente (no se simula operativo). Amazon SQS es la opción
preferente para JOBS asíncronos (separado de Redis, que se reserva para distribución de eventos SSE).

Requiere (con AWS): `SQS_QUEUE_URL`, `AWS_REGION`, credenciales por IAM Role/Task Role (nunca en Git).
"""

import json
import logging
import os

from src.services.jobs.base import Job, JobQueue

logger = logging.getLogger("jobs.sqs")


def boto3_disponible() -> bool:
    try:
        import boto3  # noqa: F401
        return True
    except Exception:
        return False


class SQSQueue(JobQueue):
    nombre = "sqs"

    def __init__(self, queue_url=None, region=None):
        if not boto3_disponible():
            raise RuntimeError("boto3 no instalado: cola SQS PREPARADA, no operativa")
        self._url = queue_url or os.getenv("SQS_QUEUE_URL")
        if not self._url:
            raise RuntimeError("SQS_QUEUE_URL no configurado")
        import boto3
        self._c = boto3.client("sqs", region_name=region or os.getenv("AWS_REGION"))
        # Config (nombres; la DLQ/visibility se fijan en la infra, aquí se leen para el driver).
        self._visibility = int(os.getenv("SQS_VISIBILITY_TIMEOUT", "300"))
        self._dlq_url = os.getenv("SQS_DLQ_URL")           # [EXTERNO] cola de mensajes muertos
        self._receipts = {}                                # job.id -> ReceiptHandle (borrado tras éxito)

    def encolar(self, job: Job) -> str:
        # MessageGroupId por tenant preserva orden por empresa y evita mezclar contextos.
        self._c.send_message(QueueUrl=self._url, MessageBody=json.dumps(job.to_dict(), default=str),
                            MessageAttributes={"id_empresa": {"DataType": "String",
                                                              "StringValue": str(job.id_empresa)}})
        return job.id

    def siguiente(self, *, timeout=0):
        # NO borra el mensaje al recibir: se confirma (`confirmar`) sólo tras procesar con éxito. Si el worker
        # muere, SQS reentrega tras el visibility timeout (at-least-once) → el guard de idempotencia evita el
        # doble efecto. Tras SQS_MAX_RECEIVE_COUNT, SQS mueve el mensaje a la DLQ automáticamente.
        r = self._c.receive_message(QueueUrl=self._url, MaxNumberOfMessages=1,
                                    WaitTimeSeconds=min(int(timeout), 20),
                                    AttributeNames=["ApproximateReceiveCount"],
                                    VisibilityTimeout=self._visibility)
        msgs = r.get("Messages", [])
        if not msgs:
            return None
        m = msgs[0]
        job = Job.from_dict(json.loads(m["Body"]))
        job.attempt = int(m.get("Attributes", {}).get("ApproximateReceiveCount", job.attempt))
        self._receipts[job.id] = m["ReceiptHandle"]
        return job

    def confirmar(self, job) -> None:
        """Borra el mensaje tras procesarlo con éxito (o como permanente/DLQ manejada)."""
        h = self._receipts.pop(job.id, None)
        if h:
            self._c.delete_message(QueueUrl=self._url, ReceiptHandle=h)

    def rechazar(self, job) -> None:
        """No borra: deja que SQS reentregue tras el visibility timeout (o mueva a DLQ al agotar intentos)."""
        self._receipts.pop(job.id, None)

    def profundidad(self) -> int:
        a = self._c.get_queue_attributes(QueueUrl=self._url,
                                        AttributeNames=["ApproximateNumberOfMessages"])
        return int(a["Attributes"].get("ApproximateNumberOfMessages", 0))
