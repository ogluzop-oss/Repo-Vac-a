"""
Gobierno Corporativo de Smart Manager AI (Paquete Enterprise 7).

Dota al ERP de estructura organizativa real: organigrama jerarquico (grupo→empresa→…→empleado),
responsables, cadenas de aprobacion, delegaciones temporales, escalado automatico, matriz de
autoridad, herencia de politicas y gobierno para la IA. REUTILIZA Workflow/BPM, AutomationService,
Auditoria, control por roles, multiempresa/multitienda. NO crea motores nuevos. Aditivo/reversible.

Punto de entrada unico:
    from src.services import gobierno
    gobierno.servicio().puede_aprobar("CAJA9", "compras", importe=7000)
    gobierno.servicio().dashboard()
"""

from src.services.gobierno import (aprobaciones, autoridad, dashboard,      # noqa: F401
                                   delegacion, escalado, gobierno_ia,
                                   organigrama, politicas, responsables)
from src.services.gobierno.motor import GovernanceService, servicio         # noqa: F401

__all__ = [
    "servicio", "GovernanceService", "organigrama", "responsables", "delegacion",
    "aprobaciones", "escalado", "autoridad", "politicas", "dashboard", "gobierno_ia",
]
