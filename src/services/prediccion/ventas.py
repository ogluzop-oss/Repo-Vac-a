"""
Prediccion de ventas (Paquete Enterprise 3, SUBFASE 3.3). Tendencias, crecimientos/caidas y
proyecciones (proximo dia/semana/mes/trimestre). Solo lectura.
"""

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C
from src.services.prediccion import estadisticas as E
from src.services.prediccion import forecasting as F
from src.services.prediccion import tendencias as T

_HORIZONTES = [("proximo dia", 1), ("proxima semana", 7), ("proximo mes", 30),
               ("proximo trimestre", 90)]


def predecir(id_empresa=None) -> dict:
    if not C.activo("ventas", id_empresa):
        return {"dominio": "ventas", "activo": False, "predicciones": [], "alertas": []}
    rows = A.ventas_por_dia(id_empresa, dias=90)
    serie = [float(v.get("total") or 0) for v in rows]
    fechas = [str(v.get("d")) for v in rows]
    tend = T.analizar(serie)
    conf = E.confianza(serie)
    # Motor predictivo REAL (`forecasting`): usa Machine Learning (Prophet) cuando hay datos suficientes,
    # si no modelo estadístico/heurístico. Etiquetado HONESTO del origen (modelo/tipo/es_ml). Un solo ajuste.
    fc = F.forecast(serie, fechas=fechas, horizonte=90, id_empresa=id_empresa, entidad="ventas",
                    emitir=False, persistir=False)
    pred = fc.get("prediccion") or []

    def _total(pasos):
        return round(sum(pred[:pasos]), 2) if pred else 0.0

    predicciones = []
    for etq, pasos in _HORIZONTES:
        c = max(0.2, conf - (0.0 if pasos <= 7 else (0.2 if pasos <= 30 else 0.3)))
        predicciones.append({"metrica": "ventas", "horizonte": etq,
                             "valor": _total(pasos), "confianza": round(c, 2),
                             "detalle": T.interpretar(tend)})
    alertas = []
    if tend["tendencia"] == "bajada" and abs(tend.get("variacion_pct", 0)) >= 20:
        alertas.append({"tipo": "ventas", "severidad": "alta",
                        "mensaje": f"Se preve una caida importante de ventas ({tend['variacion_pct']:.0f}%).",
                        "datos": tend})
    elif tend["tendencia"] == "subida" and abs(tend.get("variacion_pct", 0)) >= 20:
        alertas.append({"tipo": "ventas", "severidad": "baja",
                        "mensaje": f"Ventas en fuerte crecimiento (+{tend['variacion_pct']:.0f}%).",
                        "datos": tend})
    return {"dominio": "ventas", "activo": True, "predicciones": predicciones, "alertas": alertas,
            "tendencia": tend, "modelo": fc.get("modelo"), "tipo": fc.get("tipo"),
            "es_ml": fc.get("es_ml", False)}
