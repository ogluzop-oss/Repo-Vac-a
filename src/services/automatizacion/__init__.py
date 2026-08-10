"""
Motor de Automatizacion Empresarial de Smart Manager AI (Paquete Enterprise 4).

El ERP pasa de detectar a ACTUAR: propone, prepara, encadena, pide aprobacion y ejecuta (cuando
esta autorizado) — REUTILIZANDO Workflow/BPM/aprobaciones, Event Bus, IAService y PredictionService.
NO crea un segundo Workflow/BPM/motor de tareas. Aditivo, asincrono, idempotente, auditable,
multiempresa/multitienda.

Punto de entrada unico:
    from src.services import automatizacion
    svc = automatizacion.servicio()
    svc.procesar_evento({"tipo": "PRECIO_ACTUALIZADO", "id": 123})
    svc.tick()                      # programadas + predicciones (asincrono)
    automatizacion.panel.resumen()  # panel del Centro de Actividad
"""

from src.services.automatizacion import (acciones, cadenas, configuracion,   # noqa: F401
                                         niveles, panel, programadas, reglas)
from src.services.automatizacion.motor import AutomationService, servicio    # noqa: F401

__all__ = [
    "servicio", "AutomationService", "reglas", "acciones", "niveles", "cadenas",
    "programadas", "panel", "configuracion",
]
