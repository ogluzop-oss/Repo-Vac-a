"""
Job del scheduler para la carpeta «Programados» de Correo (circulares/encuestas internas).

No es un motor nuevo: reutiliza el scheduler empresarial existente (`services/scheduler.py` +
catálogo `services/scheduler_registry.py`, mismo patrón ya usado por SAT/GMAO/CRM/etc.). El job
`com_programados_envio` publica (estado PROGRAMADA -> PUBLICADA) toda circular/encuesta cuya
`fecha_programada` ya venció — ver `circulares.disparar_programadas_vencidas` /
`encuestas.disparar_programadas_vencidas` (migración 0288).
"""

from . import circulares, encuestas


def _job_programados_envio(id_empresa):
    r1 = circulares.disparar_programadas_vencidas(id_empresa)
    r2 = encuestas.disparar_programadas_vencidas(id_empresa)
    return f"{r1}; {r2}"


def registrar_jobs_com(id_empresa=None):
    """Registra el callable y crea el job por defecto (ligero, habilitado) de la empresa
    (idempotente). Se invoca desde `scheduler_registry.REGISTRADORES`, igual que el resto de
    dominios (SAT/GMAO/CRM/BI/...)."""
    from src.services import scheduler as _sched
    _sched.registrar("com_programados_envio", _job_programados_envio)
    _sched.registrar_job("com_programados_envio", intervalo_horas=1,
                         descripcion="Correo · envío de circulares/encuestas programadas",
                         id_empresa=id_empresa)
