"""
Modelo del Gemelo Digital (Paquete Enterprise 8). Estructuras ligeras para representar el estado
vivo de un dominio. NO son tablas: son vistas materializadas en memoria, construidas bajo demanda
desde `fuentes`. Cada estado lleva un nivel de RIESGO derivado (BAJO/MEDIO/ALTO) para el dashboard
y para que IA/Copiloto/Agentes prioricen sin recalcular.
"""

RIESGO_BAJO = "BAJO"
RIESGO_MEDIO = "MEDIO"
RIESGO_ALTO = "ALTO"

_ORDEN_RIESGO = {RIESGO_BAJO: 0, RIESGO_MEDIO: 1, RIESGO_ALTO: 2}


def peor_riesgo(*niveles) -> str:
    """Devuelve el nivel de riesgo mas alto de los indicados (para agregar dominios)."""
    peor = RIESGO_BAJO
    for n in niveles:
        if _ORDEN_RIESGO.get(n, 0) > _ORDEN_RIESGO.get(peor, 0):
            peor = n
    return peor


def estado_dominio(dominio, *, resumen="", riesgo=RIESGO_BAJO, indicadores=None,
                   alertas=None, detalle=None) -> dict:
    """Contrato uniforme de estado de un dominio del gemelo."""
    return {
        "dominio": dominio,
        "resumen": resumen,
        "riesgo": riesgo,
        "indicadores": indicadores or {},
        "alertas": alertas or [],
        "detalle": detalle or {},
    }
