"""
MEMORIA y CONTINUIDAD empresarial de SOMA (Fase 8 — madurez). Capa NUEVA que AMPLÍA lo existente sin
modificar ningún motor (SomaKernel, Overlay, Mission Engine, Especialistas, Observador, Bandeja,
Workflow, Gobierno, Autonomía). Convierte a SOMA en un compañero de trabajo con continuidad:

  · memoria empresarial a largo plazo  → conocimiento.py  (soma_empresa_conocimiento, migr 0100)
  · aprendizaje lento de hábitos        → habitos.py
  · continuidad entre días              → continuidad.py
  · reanudación de misiones             → reanudacion.py   (solo lectura sobre Fase 6)
  · personalidad adaptativa (clima)     → clima.py
  · contexto histórico                  → historico.py     (reutiliza BI KPIs)
  · respuestas multimodales             → multimodal.py    (tipos que el overlay ya renderiza)

Integración SIN tocar motores: el saludo de continuidad se emite por el camino proactivo YA existente
(`kernel.intervenir`); el aprendizaje de hábitos usa el Scheduler existente; las consultas históricas
entran por `procesar → razonador` (ampliado, no sustituido).
"""

import logging
import threading

logger = logging.getLogger("soma.empresa")

from src.soma.empresa import (clima, conocimiento, continuidad, habitos,  # noqa: E402,F401
                              historico, multimodal, reanudacion)

_saludado = False   # evita repetir el saludo de continuidad dentro de la misma sesión


def al_iniciar_sesion(kernel) -> None:
    """Enganche ADITIVO llamado desde main.py tras arrancar el kernel. (1) programa el aprendizaje de
    hábitos en el Scheduler existente y lo ejecuta una vez en segundo plano; (2) programa el saludo de
    continuidad, que se emite por el camino proactivo del kernel (sin modificarlo). A prueba de fallos."""
    try:
        _registrar_job_habitos()
    except Exception as e:
        logger.debug("job hábitos: %s", e)
    # Aprendizaje inicial de hábitos (en segundo plano, no bloquea el arranque).
    threading.Thread(target=_observar_habitos_seguro, args=(kernel,), daemon=True,
                     name="soma-habitos-init").start()
    # Saludo de continuidad unos segundos tras el login (deja que arranque la voz/overlay).
    try:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(6500, lambda: _saludar(kernel))
    except Exception as e:
        logger.debug("timer saludo: %s", e)


def _ctx(kernel):
    try:
        snap = kernel.contexto_actual()
        return snap.get("empresa"), snap.get("usuario")
    except Exception:
        return None, None


def _registrar_job_habitos():
    from src.services import scheduler
    scheduler.registrar("soma_habitos", lambda _emp=None: (habitos.observar(_emp) and "ok") or "ok")
    scheduler.registrar_job("soma_habitos", intervalo_horas=24,
                            descripcion="Aprendizaje lento de hábitos empresariales (SOMA)")


def _observar_habitos_seguro(kernel):
    try:
        emp, usuario = _ctx(kernel)
        n = habitos.observar(emp, usuario)
        logger.info("SOMA memoria empresarial: %s hábitos observados.", n)
    except Exception as e:
        logger.debug("observar hábitos: %s", e)


def _saludar(kernel):
    global _saludado
    if _saludado:
        return
    try:
        emp, usuario = _ctx(kernel)
        hz = continuidad.saludo_continuidad(emp, usuario)
        if hz is not None:
            _saludado = True
            kernel.intervenir(hz)   # camino proactivo EXISTENTE (muestra + habla + respeta no-molestar)
    except Exception as e:
        logger.debug("saludo continuidad: %s", e)
