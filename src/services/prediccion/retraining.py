"""
Retraining CONTROLADO de modelos predictivos (Fase 7). Reutiliza el motor (`forecasting`) y el ciclo de vida
(`modelos`). Detecta degradación → entrena un candidato (persistido como VALIDATED con métricas reales) →
lo compara con el activo → **activa SOLO si mejora** (menor MAE) → audita. Nunca sustituye al modelo activo
sin validación; el anterior queda DEPRECATED (rollback recuperable). No simula automatización agresiva.
"""

import logging

logger = logging.getLogger("prediccion.retraining")


def retrain(id_empresa, *, entidad="ventas", wape_reciente=None, usuario="scheduler", horizonte=30) -> dict:
    """Retraining controlado. Si `wape_reciente` indica que el modelo activo NO está degradado, no hace
    nada. En otro caso (o sin métrica reciente) entrena un candidato y lo activa solo si mejora."""
    from src.services.prediccion import forecasting, modelos
    if wape_reciente is not None:
        deg = modelos.evaluar_degradacion(id_empresa, entidad, wape_reciente)
        if deg.get("estado") not in ("MODEL_DEGRADED", "MODEL_RETRAIN_REQUIRED"):
            return {"ok": True, "accion": "ninguna", "estado": deg.get("estado")}
    # Entrena candidato: forecast_ventas persiste un nuevo modelo VALIDATED con sus métricas de backtesting.
    r = forecasting.predecir_ventas(id_empresa, horizonte=horizonte, emitir=False)
    candidato = r.get("model_id")
    if not candidato:
        return {"ok": False, "error": "no se pudo entrenar el candidato"}
    act = modelos.activar(candidato, id_empresa=id_empresa, usuario=usuario)   # activa solo si mejora
    return {"ok": True, "accion": "retrain", "candidato": candidato,
            "activado": act.get("activado", False), "comparacion": act.get("comparacion"),
            "motivo": act.get("motivo")}


def rollback(id_empresa, entidad, model_id_anterior, *, usuario="scheduler") -> dict:
    """Rollback controlado: reactiva un modelo anterior (DEPRECATED) si sigue siendo válido. Auditable."""
    from src.services.prediccion import modelos
    m = modelos.obtener(model_id_anterior)
    if not m or str(m.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "error": "modelo inexistente o de otro tenant"}
    # Se re-marca como VALIDATED y se intenta activar (la comparación decidirá).
    modelos._set_estado(model_id_anterior, "VALIDATED")
    return modelos.activar(model_id_anterior, id_empresa=id_empresa, usuario=usuario)
