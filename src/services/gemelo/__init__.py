"""
Gemelo Digital Empresarial de Smart Manager AI (Paquete Enterprise 8).

Mantiene una representacion VIVA del estado de toda la organizacion: una capa de conocimiento
construida SOBRE la base de datos (nunca la sustituye ni la duplica). Responde al instante a que
ocurre, donde, quien esta implicado, cual es el estado actual y que dependencias existen, sin
consultar continuamente decenas de modulos. Es la UNICA fuente de conocimiento de estado que usan
la IA, el Copiloto y los Agentes especializados.

Reutiliza integramente la arquitectura Enterprise (Event Bus, Centro de Actividad, Sincronizacion,
BI, PredictionService, Gobierno Corporativo, Automatizacion). Aditivo, reversible, idempotente,
multiempresa/multitienda, SaaS-ready.

Punto de entrada UNICO:
    from src.services import gemelo
    gemelo.servicio().estado_empresa()
    gemelo.servicio().estado_tienda("Valencia")
    gemelo.servicio().dashboard()
"""

from src.services.gemelo import (comercial, consistencia, consultas, dashboard,   # noqa: F401
                                 dependencias, estado_global, financiero, fuentes,
                                 inventario, logistico, rrhh, snapshot)
from src.services.gemelo.motor import DigitalTwinService, servicio               # noqa: F401

__all__ = [
    "servicio", "DigitalTwinService", "estado_global", "inventario", "comercial",
    "rrhh", "financiero", "logistico", "dependencias", "consultas", "consistencia",
    "dashboard", "snapshot", "fuentes",
]
