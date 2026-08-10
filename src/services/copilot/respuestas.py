"""
Respuestas enriquecidas y explicables (Paquete Enterprise 5, SUBFASE 5.5/5.7/5.8). Combina la
respuesta base (IA/Prediccion) con: fuentes (de donde procede — 5.7), recomendaciones y alertas
contextuales SOLO si hay evidencia (5.8). Nunca inventa: todo procede de servicios reales.
"""

import logging

logger = logging.getLogger("copilot.respuestas")

_FUENTES = {
    "resumen": ["Centro de Actividad", "IAService"],
    "reposicion": ["IAService", "Inventario"],
    "ventas": ["Ventas", "IAService"],
    "facturas_pendientes": ["Facturacion"],
    "anomalias": ["IAService"],
    "contratos": ["RRHH"],
    "sincronizacion": ["Sincronizacion Enterprise"],
    "exceso_stock": ["Inventario"],
    "prediccion": ["PredictionService"],
    "accion": ["AutomationService", "Workflow/BPM"],
}


def fuentes(intent) -> list:
    s = str(intent or "")
    for k, v in _FUENTES.items():
        if k in s:
            return v
    return ["IAService"]


def enriquecer(base, ctx, id_empresa) -> dict:
    intent = base.get("intent", "")
    fs = fuentes(intent)
    reco, alertas = [], []
    # SUBFASE 5.8: recomendaciones/alertas contextuales SOLO si existen (evidencia real).
    try:
        from src.services import prediccion
        alertas = prediccion.servicio().alertas(id_empresa)[:3]
    except Exception:
        pass
    try:
        from src.services import ia
        reco = ia.servicio().recomendaciones(id_empresa, limite=3)
    except Exception:
        pass
    if "prediccion" in intent or intent in ("ventas", "stock"):
        fs = fs + ["PredictionService"]
    # Preserva las fuentes que ya aporto el agente especialista (SUBFASE 6.14 explicabilidad).
    fs = sorted(set(fs + list(base.get("fuentes") or [])))
    return {**base, "fuentes": fs, "recomendaciones_contextuales": reco,
            "alertas_contextuales": alertas, "contexto": ctx}
