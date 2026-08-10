"""
Enterprise Scheduler (Fase III · B3) — fachada pública.

    from src.services import scheduler_enterprise as sched
    sched.registrar_job("informe_diario", lambda p: generar_informe(p))
    sid = sched.crear_schedule("Informe diario", "informe_diario", tipo="diaria", id_empresa=...)
    sched.ejecutar_schedule(sid)      # o sched.procesar_pendientes()

Persistente, con reintentos/prioridades/cancelación/auditoría. API-First (sin PyQt).
"""

from src.services.scheduler_enterprise.core import (  # noqa: F401
    registrar_job, crear_schedule, listar_schedules, cancelar, pausar, reanudar,
    ejecutar_schedule, procesar_pendientes,
)
from src.services.scheduler_enterprise import calendario as calendario  # noqa: F401

__all__ = ["registrar_job", "crear_schedule", "listar_schedules", "cancelar", "pausar", "reanudar",
           "ejecutar_schedule", "procesar_pendientes", "calendario"]
