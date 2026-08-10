"""
Riesgo por escenario (Paquete Enterprise 9, SUBFASE 9.9). PredictionService recalcula el riesgo
para CADA escenario a partir de las metricas simuladas — nunca se reutiliza el riesgo real tal
cual. Se parte del riesgo base (PredictionService, solo lectura) y se AJUSTA segun los deltas del
escenario (beneficio, liquidez, roturas, margen). Todo virtual.
"""

import logging

logger = logging.getLogger("simulador.riesgo")

_ORDEN = {"BAJO": 0, "MEDIO": 1, "ALTO": 2}
_INV = {0: "BAJO", 1: "MEDIO", 2: "ALTO"}


def _base_riesgos(id_empresa):
    try:
        from src.services import prediccion
        return prediccion.servicio().riesgos(id_empresa)
    except Exception as e:
        logger.debug("riesgos base: %s", e)
        return []


def evaluar(id_empresa, base_metricas, sim_metricas) -> dict:
    """Recalcula el riesgo del escenario. Devuelve nivel global + factores explicables."""
    factores = []
    nivel = 0

    # Riesgo financiero: caida de beneficio o liquidez negativa simulada.
    ben_b = float(base_metricas.get("beneficio", 0) or 0)
    ben_s = float(sim_metricas.get("beneficio", 0) or 0)
    if ben_s < 0:
        nivel = max(nivel, 2); factores.append("Beneficio simulado NEGATIVO")
    elif ben_b and ben_s < ben_b * 0.9:
        nivel = max(nivel, 1); factores.append(f"Beneficio cae {round((1-ben_s/ben_b)*100,1)}%")

    liq_s = float(sim_metricas.get("liquidez", 0) or 0)
    if liq_s < 0:
        nivel = max(nivel, 2); factores.append("Liquidez simulada NEGATIVA")

    # Riesgo operativo: roturas de stock simuladas.
    rot_s = int(sim_metricas.get("stock_roturas", 0) or 0)
    if rot_s > 5:
        nivel = max(nivel, 2); factores.append(f"{rot_s} roturas de stock previstas")
    elif rot_s > 0:
        nivel = max(nivel, 1); factores.append(f"{rot_s} roturas de stock previstas")

    # Riesgo de margen.
    mar_s = float(sim_metricas.get("margen_pct", 0) or 0)
    if mar_s < 5:
        nivel = max(nivel, 1); factores.append(f"Margen simulado bajo ({mar_s}%)")

    # Contexto del riesgo real (informativo, NO se reutiliza como resultado).
    base_ctx = len(_base_riesgos(id_empresa))
    return {
        "nivel": _INV[nivel],
        "factores": factores or ["Sin factores de riesgo relevantes en el escenario."],
        "riesgos_reales_contexto": base_ctx,
        "recalculado": True,
    }
