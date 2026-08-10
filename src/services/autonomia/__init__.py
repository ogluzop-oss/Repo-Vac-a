"""
Autonomia Supervisada de Smart Manager AI (Paquete Enterprise 10 — cierre del bloque Enterprise).

Convierte Smart Manager AI en un sistema capaz de EJECUTAR acciones reales de forma SUPERVISADA. El
sistema nunca actua libremente: toda accion esta gobernada por reglas, permisos, niveles de
autoridad, Workflow/BPM y Gobierno Corporativo. La IA propone, la organizacion decide, el sistema
ejecuta unicamente lo autorizado. Las acciones criticas nunca se auto-ejecutan (se proponen).

Reutiliza integramente: Event Bus, Centro de Actividad, Workflow/BPM, Gobierno Corporativo,
AutomationService, CopilotService, AgentManager, IAService, PredictionService, DigitalTwinService,
SimulationService. Aditivo, reversible, idempotente, multiempresa/multitienda, SaaS-ready.

Punto de entrada UNICO (unico servicio autorizado a ejecutar):
    from src.services import autonomia
    pid = autonomia.servicio().plan_desde_escenario(id_escenario)
    autonomia.servicio().solicitar_aprobacion(pid)
    autonomia.servicio().aprobar_plan(pid, usuario="ADMIN", perfil="ADMINISTRADOR")
    autonomia.servicio().ejecutar(pid, usuario="ADMIN", perfil="ADMINISTRADOR", solo_fase=1)
"""

from src.services.autonomia import (agentes_revision, catalogo, dashboard,       # noqa: F401
                                    ejecucion, explicabilidad, indicador, modos,
                                    planes, seguridad, validaciones)
from src.services.autonomia.motor import ExecutiveActionService, servicio        # noqa: F401

__all__ = [
    "servicio", "ExecutiveActionService", "planes", "ejecucion", "validaciones",
    "modos", "catalogo", "seguridad", "explicabilidad", "agentes_revision",
    "indicador", "dashboard",
]
