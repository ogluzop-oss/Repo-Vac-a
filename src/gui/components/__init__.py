"""
gui/components — librería visual ÚNICA del sistema Enterprise de Smart Manager AI.

Depende de `gui/foundation` (tokens, iconos, export). NUNCA al revés (Foundation → Components →
Panels → Windows). Prohibido crear tablas, buscadores, tarjetas, filtros, toolbars, badges o
indicadores fuera de esta librería (salvo justificación técnica documentada). Todo desarrollo nuevo
reutiliza estos componentes.
"""

from src.gui.components.enterprise import (  # noqa: F401
    EnterpriseCard, EnterpriseDashboardGrid, EnterpriseFilter, EnterpriseRiskIndicator,
    EnterpriseSearch, EnterpriseStatusBadge, EnterpriseTable, EnterpriseTimeline,
    EnterpriseToolbar)

__all__ = [
    "EnterpriseCard", "EnterpriseDashboardGrid", "EnterpriseFilter", "EnterpriseRiskIndicator",
    "EnterpriseSearch", "EnterpriseStatusBadge", "EnterpriseTable", "EnterpriseTimeline",
    "EnterpriseToolbar",
]
