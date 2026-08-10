"""
Centro de Actividad Empresarial (Fase 3) — capa de experiencia sobre el Event Bus.

Backend desacoplado que alimenta:
  • badges       → circulos rojo estilo WhatsApp, calculados desde la cola de eventos.
  • timeline     → linea de tiempo de toda la actividad del ERP.
  • historial    → traza completa de un cambio (quien/cuando/desde donde/aplicado).
  • sincronizacion → estado por terminal (sincronizada/pendiente/offline).

Todo se filtra por empresa (multiempresa real) y por alcance del usuario. Preparado para que
una IA empresarial consulte y resuma la actividad (SUBFASE 3.10).
"""

from src.services.actividad import (agrupacion, badges, busqueda,       # noqa: F401
                                    ejecutiva, favoritos, filtros,
                                    historial, mapeo, scope, sincronizacion,
                                    timeline)
from src.services.actividad.badges import (contar, marcar_visto,        # noqa: F401
                                           total)

__all__ = [
    "contar", "total", "marcar_visto",
    "badges", "timeline", "historial", "sincronizacion", "scope", "mapeo",
    "agrupacion", "filtros", "busqueda", "favoritos", "ejecutiva",
]
