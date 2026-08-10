"""
Corporate Rules Engine (Fase III · B5) — fachada pública.

    from src.services import rules
    rules.crear_regla("Factura grande", evento="InvoiceGenerated",
                      condiciones=[{"campo":"importe","op":">","valor":5000}],
                      acciones=[{"tipo":"lanzar_evento","evento":"BigInvoice"},
                                {"tipo":"notificar","titulo":"Factura alta","roles":["GERENTE"]}])
    rules.evaluar_evento("InvoiceGenerated", {"importe": 6000}, id_empresa=...)

Reglas SIN código (datos). Toda acción pasa por los servicios (CCP/eventos/notificaciones/workflow).
API-First (sin PyQt).
"""

from src.services.rules.rule_engine import (  # noqa: F401
    crear_regla, listar_reglas, activar, evaluar_evento, suscribir_al_bus,
)
from src.services.rules import conditions as conditions  # noqa: F401
from src.services.rules import actions as actions  # noqa: F401

__all__ = ["crear_regla", "listar_reglas", "activar", "evaluar_evento", "suscribir_al_bus",
           "conditions", "actions"]
