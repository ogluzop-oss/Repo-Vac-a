"""
Motor interno de estimacion (Paquete Enterprise 3, SUBFASE 3.14 — PREPARACION ML).

Define el contrato `Estimador` y una implementacion HEURISTICA por defecto (media movil +
proyeccion lineal). El motor interno es ENCHUFABLE: en el futuro se podra sustituir por Prophet,
XGBoost, Random Forest, redes neuronales o LLMs especializados SIN tocar PredictionService —
basta con `set_estimador(mi_estimador)`.
"""

from src.services.prediccion import estadisticas as E


class Estimador:
    """Contrato del motor de estimacion. Devuelve el TOTAL previsto para `pasos` periodos."""
    nombre = "base"

    def predecir(self, valores, pasos=1) -> float:
        raise NotImplementedError


class EstimadorHeuristico(Estimador):
    nombre = "heuristico"

    def _paso(self, valores) -> float:
        if not valores:
            return 0.0
        mm = E.media_movil(valores, 7)
        proj = E.proyeccion(valores, 1)
        # Serie corta → media movil; serie amplia → mezcla con proyeccion lineal.
        base = mm if len(valores) < 4 else (0.6 * mm + 0.4 * proj)
        return max(0.0, base)

    def predecir(self, valores, pasos=1) -> float:
        return round(self._paso(valores) * max(1, int(pasos)), 2)


_ESTIMADOR = EstimadorHeuristico()


def estimador() -> Estimador:
    return _ESTIMADOR


def set_estimador(nuevo: Estimador) -> None:
    """Sustituye el motor interno (Prophet/XGBoost/RandomForest/NN/LLM) sin tocar el resto."""
    global _ESTIMADOR
    _ESTIMADOR = nuevo


# Nombres de estimadores que son HEURÍSTICOS (no ML). Cualquier otro nombre se considera un modelo ML.
_NOMBRES_HEURISTICOS = frozenset({"base", "heuristico"})


def motor_activo() -> dict:
    """Identifica HONESTAMENTE el origen de las predicciones para que la UI/SOMA/dashboards nunca
    presenten una heurística como IA/ML. Devuelve `{motor, tipo, es_ml}` donde `tipo` ∈ {'heuristica','ml'}.

    Regla (Fase IA): mientras el estimador activo sea el heurístico por defecto, `es_ml=False` y debe
    etiquetarse como "estimación heurística", NO como "IA/ML". Al enchufar Prophet/XGBoost/… vía
    `set_estimador`, el nombre del estimador pasa a identificar el modelo real (`es_ml=True`)."""
    nombre = getattr(estimador(), "nombre", "base") or "base"
    es_ml = nombre not in _NOMBRES_HEURISTICOS
    return {"motor": nombre, "tipo": "ml" if es_ml else "heuristica", "es_ml": es_ml}


def predecir(valores, pasos=1) -> float:
    return _ESTIMADOR.predecir(valores, pasos)
