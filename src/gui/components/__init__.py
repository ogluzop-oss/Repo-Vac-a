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
# Kanban vive en su propio módulo (no en enterprise.py): es un widget de arrastrar-y-soltar con
# lógica de drag&drop propia, no una variante más de tarjeta/tabla — ver justificación en
# `kanban.py`. Re-exportado aquí para que el resto de la app lo importe igual que el resto de la
# librería (`from src.gui.components import EnterpriseKanbanBoard`).
from src.gui.components.kanban import EnterpriseKanbanBoard  # noqa: F401

__all__ = [
    "EnterpriseCard", "EnterpriseDashboardGrid", "EnterpriseFilter", "EnterpriseRiskIndicator",
    "EnterpriseSearch", "EnterpriseStatusBadge", "EnterpriseTable", "EnterpriseTimeline",
    "EnterpriseToolbar", "EnterpriseKanbanBoard",
]
