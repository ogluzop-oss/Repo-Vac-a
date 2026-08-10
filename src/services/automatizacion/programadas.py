"""
Automatizaciones programadas (Paquete Enterprise 4, SUBFASE 4.6). Reutiliza el scheduler
existente: no crea un motor horario nuevo. Registra jobs diario/semanal/mensual que ejecutan las
reglas programadas correspondientes.
"""

import logging

logger = logging.getLogger("automatizacion.programadas")


def registrar_jobs(id_empresa=None) -> bool:
    try:
        from src.services import scheduler
        from src.services.automatizacion import motor

        scheduler.registrar("automatizacion_diaria",
                            lambda **_k: motor.servicio().procesar_programadas(id_empresa, "diario"))
        scheduler.registrar("automatizacion_semanal",
                            lambda **_k: motor.servicio().procesar_programadas(id_empresa, "semanal"))
        scheduler.registrar("automatizacion_mensual",
                            lambda **_k: motor.servicio().procesar_programadas(id_empresa, "mensual"))
        try:
            scheduler.registrar_job("automatizacion_diaria", intervalo_horas=24,
                                    descripcion="Automatizaciones diarias", id_empresa=id_empresa)
            scheduler.registrar_job("automatizacion_semanal", intervalo_horas=168,
                                    descripcion="Automatizaciones semanales", id_empresa=id_empresa)
        except Exception as e:
            logger.debug("registrar_job automatizacion: %s", e)
        return True
    except Exception as e:
        logger.warning("registrar_jobs automatizacion: %s", e)
        return False
