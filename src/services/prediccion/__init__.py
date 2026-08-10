"""
Motor Predictivo Empresarial de Smart Manager AI (Paquete Enterprise 3).

Evoluciona la plataforma de EXPLICAR el pasado/presente a ANTICIPAR el futuro: prediccion de
stock/ventas/compras/tesoreria/RRHH/CRM, indice de riesgo multivariable, tendencias, alertas
predictivas y dashboard. DESACOPLADO y ADITIVO: se apoya en `ia.adaptadores`, BI, Event Bus y BD
existentes (sin duplicar ni crear BBDD paralelas). SOLO LEE: nunca ejecuta ni escribe en el ERP;
toda actuacion pasa por Workflow/BPM o el usuario. ML-ready: el motor interno (heuristicas) es
enchufable (Prophet/XGBoost/RandomForest/NN/LLM) sin tocar PredictionService.

Punto de entrada unico:
    from src.services import prediccion
    svc = prediccion.servicio()
    svc.panel_predictivo()
    svc.responder_futuro("¿que productos tendran rotura?")
"""

from src.services.prediccion import (adaptadores, clientes, compras,      # noqa: F401
                                     configuracion, estadisticas,
                                     heuristicas, indicadores, riesgos,
                                     rrhh, stock, tendencias, tesoreria,
                                     ventas)
from src.services.prediccion.motor import PredictionService, servicio     # noqa: F401
from src.services.prediccion import forecasting                          # noqa: F401

__all__ = [
    "servicio", "PredictionService", "configuracion", "heuristicas",
    "stock", "ventas", "compras", "tesoreria", "rrhh", "clientes",
    "riesgos", "indicadores", "tendencias", "estadisticas", "adaptadores",
]
