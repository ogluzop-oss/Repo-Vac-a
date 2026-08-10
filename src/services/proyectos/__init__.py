"""
Gestión de proyectos — Kanban/Gantt + rentabilidad por costes/horas.

Capas: `proyectos` (CRUD), `tareas` (tablero Kanban + cronograma Gantt), `seguimiento` (horas, costes y
rentabilidad). Toda la lógica vive aquí; la GUI (`gui/proyectos_gui.py`) solo orquesta. RBAC `proyectos.*`.
"""

from src.services.proyectos import proyectos, seguimiento, tareas

__all__ = ["proyectos", "tareas", "seguimiento"]
