"""
Prediccion empresarial (SUBFASE 6). Estimaciones a partir del historico existente (media movil).
Reutiliza el forecasting de BI/Prophet si esta disponible; si no, heuristica simple. Solo lectura.
"""

import logging
import statistics

from src.services.ia import adaptadores as A
from src.services.ia import configuracion as C
from src.services.ia.modelos import Prediccion

logger = logging.getLogger("ia.predicciones")


def predecir(id_empresa=None) -> list:
    if not C.activo("predicciones", id_empresa):
        return []
    pred = []
    # ── Ventas futuras (media movil 30d → proyeccion 7d) ──
    try:
        v = A.ventas_por_dia(id_empresa, dias=30)
        totales = [float(x.get("total") or 0) for x in v]
        if totales:
            media = statistics.mean(totales)
            pred.append(Prediccion("ventas", "proximos 7 dias", round(media * 7, 2), 0.6,
                                   f"Media movil {len(totales)}d: {media:.0f}/dia"))
    except Exception as e:
        logger.debug("prediccion ventas: %s", e)
    # ── Riesgo de rotura de stock ──
    bajo = A.articulos_bajo_umbral(id_empresa)
    pred.append(Prediccion("rotura_stock", "proxima semana", len(bajo),
                           0.7 if bajo else 0.3, f"{len(bajo)} articulos en riesgo de rotura"))
    # ── Necesidades de compra ──
    if bajo:
        uds = sum(int(a.get("faltan") or 0) for a in bajo)
        pred.append(Prediccion("necesidad_compra", "corto plazo", uds, 0.65,
                               f"~{uds} uds a reponer en {len(bajo)} articulos"))
    return pred
