"""
Capa de IA Empresarial de Smart Manager AI — analisis, prediccion y asistencia.

DESACOPLADA y ADITIVA: se apoya 100% en la infraestructura existente (Event Bus, Centro de
Actividad, Timeline, distribucion/sync, BI y BD) SIN crear tablas ni duplicar datos. La IA solo
LEE / analiza / explica / predice / recomienda; nunca modifica datos ni ejecuta Workflow — las
decisiones son humanas o via Workflow/BPM. Multiempresa/multitienda/SaaS.

Punto de entrada unico:
    from src.services import ia
    svc = ia.servicio()
    svc.panel_centro(usuario=..., perfil=...)     # bloque IA del Centro de Actividad
    svc.preguntar("¿que productos necesitan reposicion?")
"""

from src.services.ia import (adaptadores, analisis, anomalias, cache,      # noqa: F401
                             configuracion, consultas, modelos, predicciones,
                             recomendaciones, resumenes, riesgos)
from src.services.ia.motor import IAService, servicio                      # noqa: F401

__all__ = [
    "servicio", "IAService", "configuracion", "resumenes", "anomalias",
    "recomendaciones", "predicciones", "riesgos", "analisis", "consultas",
    "adaptadores", "modelos", "cache",
]
