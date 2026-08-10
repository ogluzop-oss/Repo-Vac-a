"""
Mission Engine de SOMA (Fase 6). SOMA deja de ser un asistente conversacional y actúa como Director
de Orquesta: recibe OBJETIVOS, los convierte en MISIONES (tareas + dependencias), coordina a los
Especialistas IA (AgentManager), ejecuta en paralelo lo independiente, consolida una única respuesta
y solicita aprobaciones (Workflow/Gobierno/Autonomía) cuando procede. El usuario habla SOLO con SOMA.

Reutiliza: AgentManager, PredictionService, Gemelo, Simulador, Workflow, Gobierno, Autonomía,
Scheduler, Event Bus, memoria/contexto/personalidad. No crea sistemas paralelos.
"""

from src.soma.mission.motor import MissionEngine, engine  # noqa: F401

__all__ = ["MissionEngine", "engine"]
