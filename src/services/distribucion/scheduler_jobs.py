"""
Jobs programados de distribucion (Fase 2). Registra en el scheduler existente:
  • distribucion_ventana    → distribuye lo PROGRAMADO en la ventana de mantenimiento.
  • distribucion_reintentos → reprocesa reintentos vencidos.
  • distribucion_tick       → drena el bus + criticos (cadencia corta).
Best-effort: si el scheduler no esta disponible, no rompe nada.
"""

import logging

logger = logging.getLogger("distribucion.jobs")


def registrar_jobs(id_empresa=None) -> bool:
    """Registra los manejadores y da de alta los jobs (idempotente)."""
    try:
        from src.services import scheduler
        from src.services.distribucion import motor

        scheduler.registrar("distribucion_ventana", lambda **_k: motor.distribuir_programados(id_empresa))
        scheduler.registrar("distribucion_reintentos", lambda **_k: motor.procesar_reintentos(id_empresa))
        scheduler.registrar("distribucion_tick", lambda **_k: motor.tick(id_empresa))
        try:
            scheduler.registrar_job("distribucion_ventana", intervalo_horas=24,
                                    descripcion="Distribucion programada (ventana de mantenimiento)",
                                    id_empresa=id_empresa)
            scheduler.registrar_job("distribucion_reintentos", intervalo_horas=1,
                                    descripcion="Reintentos de distribucion", id_empresa=id_empresa)
        except Exception as e:
            logger.debug("registrar_job distribucion: %s", e)
        return True
    except Exception as e:
        logger.warning("registrar_jobs distribucion no disponible: %s", e)
        return False
