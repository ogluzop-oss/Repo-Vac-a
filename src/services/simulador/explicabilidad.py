"""
Explicabilidad de la simulacion (Paquete Enterprise 9, SUBFASE 9.15). Toda simulacion declara:
hipotesis, variables modificadas, servicios utilizados, consecuencias calculadas (cadena causal) y
nivel de confianza. El simulador nunca da un numero sin decir de donde sale.
"""

from src.services.simulador import base as B


SERVICIOS = ["DigitalTwinService (estado base)", "PredictionService (riesgo/propagacion)",
             "BI (KPIs)", "Simulador what-if (heuristicas de elasticidad)"]


def construir(variables, cadena, confianza) -> dict:
    return {
        "hipotesis": B.hipotesis(),
        "variables_modificadas": [{"variable": v.get("variable"), "dominio": v.get("dominio"),
                                   "valor": v.get("valor")} for v in variables],
        "servicios_utilizados": SERVICIOS,
        "consecuencias_calculadas": cadena,
        "nivel_confianza": confianza,
        "aviso": ("Simulacion VIRTUAL sobre el Gemelo Digital. No modifica ningun dato real. "
                  "Las cifras derivan de heuristicas de elasticidad y de las hipotesis declaradas."),
    }
