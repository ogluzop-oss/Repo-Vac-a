"""
Copiloto Empresarial IA de Smart Manager AI (Paquete Enterprise 5).

Punto UNICO de interaccion en lenguaje natural con toda la plataforma. NO es una IA paralela: es
un ORQUESTADOR que reutiliza por completo IAService, PredictionService, AutomationService, Centro
de Actividad, Workflow/BPM, BI y Event Bus. Respuestas explicables (fuentes reales), con contexto,
memoria conversacional, recomendaciones y acciones orquestadas, respetando permisos por rol.
Aditivo, multiempresa/multitienda, SaaS-ready. Nunca inventa: solo datos reales o predicciones
fundamentadas.

Punto de entrada unico:
    from src.services import copilot
    copilot.servicio().preguntar("¿como van las ventas?", usuario=..., id_empresa=...)
    copilot.servicio().panel(usuario=...)
"""

from src.services.copilot import (acciones, contexto, intencion, memoria,    # noqa: F401
                                  respuestas, seguridad)
from src.services.copilot.motor import CopilotService, servicio              # noqa: F401

__all__ = [
    "servicio", "CopilotService", "contexto", "memoria", "intencion",
    "seguridad", "acciones", "respuestas",
]
