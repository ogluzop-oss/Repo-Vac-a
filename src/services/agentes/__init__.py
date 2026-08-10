"""
Agentes Especializados IA de Smart Manager AI (Paquete Enterprise 6).

El Copiloto (punto unico de entrada) delega cada consulta al AGENTE ESPECIALISTA mas adecuado.
No son IAs independientes: cada agente aporta conocimiento especializado REUTILIZANDO IAService,
PredictionService, AutomationService, Centro de Actividad y BI. Colaboran entre si y ofrecen
respuestas explicables. Aditivo, extensible (nuevos agentes sin tocar la arquitectura),
multiempresa/multitienda.

Uso (a traves del Copiloto):
    from src.services.agentes import manager
    manager().delegar("ventas", "¿como van las ventas?", ctx)
    manager().coordinar("¿que deberia hacer hoy?", ctx)
    manager().panel()
"""

from src.services.agentes import base, especialistas          # noqa: F401
from src.services.agentes.manager import AgentManager, manager  # noqa: F401

__all__ = ["manager", "AgentManager", "base", "especialistas"]
