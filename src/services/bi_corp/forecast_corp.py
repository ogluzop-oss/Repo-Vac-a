"""
FASE F — Analitica predictiva corporativa. Reutiliza el patron Prophet/media movil del proyecto
sobre series del DW (dw_hechos). Devuelve prediccion + confianza + tendencia + riesgo por metrica.
Degradable: media movil si Prophet no esta o hay pocos puntos.
"""

import logging
from src.services.bi_corp import olap
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.forecast")

# dominio de negocio -> (dominio DW, metrica)
SERIES = {
    "ventas": ("ventas", "facturacion"),
    "compras": ("compras", "gasto_total"),
    "stock": ("stock", "valor"),
    "tesoreria": ("tesoreria", "disponible"),
    "rrhh": ("rrhh", "coste_laboral"),
    "produccion": ("produccion", "unidades_producidas"),
    "incidencias": ("sat", "tickets_abiertos"),
}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _serie_periodos(dominio, metrica, eid, n=24):
    filas = olap.cubo(dimensiones=("periodo",), filtros={"dominio": dominio, "metrica": metrica},
                      agregacion="sum", id_empresa=eid, limite=n)
    # cubo ordena por valor; reordenar por periodo asc
    serie = sorted([(f["periodo"], float(f["valor"])) for f in filas], key=lambda x: x[0])
    return serie


def forecast(area, *, horizonte=3, id_empresa=None) -> dict:
    """Forecast de una area de negocio. Devuelve prediccion/confianza/tendencia/riesgo."""
    eid = _emp(id_empresa)
    if area not in SERIES:
        return {"ok": False, "error": "area desconocida"}
    dom, met = SERIES[area]
    serie = _serie_periodos(dom, met, eid)
    vals = [v for _, v in serie]
    if len(vals) < 3:
        media = round(sum(vals) / len(vals), 2) if vals else 0.0
        return {"ok": True, "area": area, "metodo": "media", "prediccion": [media] * horizonte,
                "confianza": "baja", "tendencia": "estable", "riesgo": "desconocido", "puntos": len(vals)}
    # Prophet si disponible.
    metodo, pred = "media_movil", None
    try:
        from prophet import Prophet  # noqa
        import pandas as pd
        import datetime as _dt
        df = pd.DataFrame({"ds": pd.date_range(end=_dt.date.today(), periods=len(vals), freq="M"), "y": vals})
        m = Prophet(weekly_seasonality=False, daily_seasonality=False, yearly_seasonality=False); m.fit(df)
        fc = m.predict(m.make_future_dataframe(periods=horizonte, freq="M")).tail(horizonte)["yhat"].tolist()
        pred = [round(max(0, v), 2) for v in fc]; metodo = "prophet"
    except Exception:
        media = sum(vals[-3:]) / 3
        pred = [round(media, 2)] * horizonte
    # Tendencia y riesgo (explicable, sobre la serie real).
    tendencia = "subiendo" if vals[-1] > vals[0] else "bajando" if vals[-1] < vals[0] else "estable"
    media = sum(vals) / len(vals)
    desv = (sum((x - media) ** 2 for x in vals) / len(vals)) ** 0.5
    cv = desv / media if media else 0
    confianza = "alta" if cv < 0.15 else "media" if cv < 0.4 else "baja"
    riesgo = "alto" if (area in ("ventas", "tesoreria") and tendencia == "bajando") else \
             "alto" if (area in ("compras", "incidencias", "stock") and tendencia == "subiendo") else "bajo"
    return {"ok": True, "area": area, "metodo": metodo, "prediccion": pred, "confianza": confianza,
            "tendencia": tendencia, "riesgo": riesgo, "puntos": len(vals), "variabilidad": round(cv, 3)}


def forecast_global(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    return {area: forecast(area, id_empresa=eid) for area in SERIES}
