"""
Simulador Empresarial de Smart Manager AI (Paquete Enterprise 9).

Responde "¿que ocurriria si...?" SIN modificar jamas los datos reales. Trabaja sobre el Gemelo
Digital como estado base y propaga consecuencias con heuristicas de elasticidad + PredictionService.
Herramienta de planificacion estrategica y what-if de nivel Enterprise.

Reutiliza integramente: DigitalTwinService, PredictionService, AutomationService, IAService,
CopilotService, AgentManager, Gobierno Corporativo, Event Bus, Workflow/BPM, BI. Aditivo,
reversible, idempotente, multiempresa/multitienda, SaaS-ready. Todo VIRTUAL (SUBFASE 9.16).

Punto de entrada UNICO:
    from src.services import simulador
    r = simulador.servicio().simular_directo([{"variable":"precio","valor":5}])
    eid = simulador.servicio().crear_escenario("Subida 5%")
    simulador.servicio().añadir_variable(eid, "precio", 5)
    simulador.servicio().simular(eid)
"""

from src.services.simulador import (base, comparador, dominios, escenarios,      # noqa: F401
                                    explicabilidad, lenguaje, propagacion, riesgo,
                                    seguridad, variables)
from src.services.simulador.motor import SimulationService, servicio             # noqa: F401

__all__ = [
    "servicio", "SimulationService", "escenarios", "variables", "propagacion",
    "riesgo", "comparador", "explicabilidad", "seguridad", "dominios", "base",
]
