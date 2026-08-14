"""
Tests · Motor de forecasting unificado (Fase 5 · IA predictiva real).

Verifica con MATEMÁTICA REAL (sin mocks del flujo): calidad de datos, selección automática de modelo
(heurística/estadística/Prophet), rechazo de Prophet por datos insuficientes, Prophet REAL cuando procede,
backtesting temporal + métricas (MAE/RMSE/WAPE), explicabilidad honesta (nunca llama IA a una heurística) y
la integración con el Event Bus + tiempo real (una predicción emite `prediccion.generada`).

NOTA: las series numéricas de estos tests son FIXTURES matemáticas de test (no datos empresariales reales);
sirven para validar la matemática del motor, no para afirmar que la IA funciona sobre datos de clientes.
"""

import datetime

import pytest


def test_calidad_datos():
    from src.services.prediccion import forecasting as F
    assert F.calidad_datos([1, 2, 3]).get("estado") == F.CAL_INSUFFICIENT       # <7 obs
    assert F.calidad_datos([5] * 20).get("estado") == F.CAL_WARNING             # serie constante
    assert F.calidad_datos([10, 12, 11, 13, 9, 14, 12, 11]).get("estado") == F.CAL_GOOD
    assert F.calidad_datos([object()] * 10).get("estado") == F.CAL_INVALID       # no numéricos


def test_seleccion_heuristica_por_falta_de_datos():
    from src.services.prediccion import forecasting as F
    r = F.forecast([10, 12, 11, 13, 9, 14, 12, 11, 10, 12], horizonte=5, id_empresa=None, emitir=False)
    assert r["modelo"] == "media_movil" and r["tipo"] == "heuristica" and r["es_ml"] is False
    assert "heurística" in r["explicacion"].lower()
    assert len(r["prediccion"]) == 5


def test_seleccion_estadistica_y_backtest():
    from src.services.prediccion import forecasting as F
    # 30 obs con tendencia → modelo estadístico (lineal), NO ML, con métricas de backtesting reales.
    vals = [100 + i * 0.8 for i in range(30)]
    r = F.forecast(vals, horizonte=7, id_empresa=None, emitir=False)
    assert r["modelo"] == "tendencia_lineal" and r["tipo"] == "estadistica" and r["es_ml"] is False
    m = r["metricas"]
    assert "mae" in m and "rmse" in m and "wape" in m
    assert isinstance(m["mae"], (int, float)) and m["rmse"] >= 0
    assert r["estado_modelo"] == "VALIDATED"
    assert r["model_not_applicable"]["prophet"] is True       # <60 obs → Prophet no aplicable


def test_prophet_real_cuando_procede():
    pytest.importorskip("prophet")            # degradable: si Prophet no está instalado, se omite
    # Prophet puede IMPORTARSE pero no poder FITEAR si le falta el backend Stan (cmdstan) — p. ej. en
    # CI. Ahí el motor degrada HONESTAMENTE a lineal, así que probamos primero un fit real: si no
    # fitea, omitimos (no es fallo de producto); si SÍ fitea, exigimos que el motor use Prophet.
    import pandas as _pd
    try:
        from prophet import Prophet as _P
        _P().fit(_pd.DataFrame({"ds": _pd.date_range("2025-01-01", periods=30),
                                "y": [float(i) for i in range(30)]}))
    except Exception as e:                     # backend Stan no operativo en este entorno
        pytest.skip(f"Prophet no puede fitear aquí (backend Stan): {e}")
    from src.services.prediccion import forecasting as F
    base = datetime.date(2025, 1, 1)
    fechas = [str(base + datetime.timedelta(days=i)) for i in range(75)]
    # FIXTURE de test: tendencia + patrón semanal (fin de semana +10). Datos sintéticos de test.
    vals = [100 + i * 0.5 + (10 if (i % 7) in (5, 6) else 0) for i in range(75)]
    r = F.forecast(vals, fechas=fechas, horizonte=7, id_empresa=None, emitir=False)
    assert r["modelo"] == "prophet" and r["tipo"] == "ml" and r["es_ml"] is True
    assert len(r["prediccion"]) == 7
    assert r["intervalo_superior"][0] >= r["prediccion"][0] >= r["intervalo_inferior"][0]
    assert "Prophet" in r["explicacion"]


def test_prophet_rechazado_por_datos_insuficientes():
    from src.services.prediccion import forecasting as F
    r = F.forecast([10, 11, 12, 13, 12, 11, 10, 12, 13, 14, 12, 11], horizonte=5, emitir=False)
    assert r["modelo"] != "prophet" and r["es_ml"] is False    # <60 obs → nunca Prophet


def test_prediccion_emite_evento_realtime(db):
    """Fase 5 → 10 → 11: una predicción publica un evento REAL que llega por el hub de tiempo real."""
    from src.services.eventbus import realtime
    from src.services.prediccion import forecasting as F
    c = realtime.registrar("PRED-A", canales=["prediccion"])
    try:
        F.forecast([10, 12, 11, 13, 10, 12, 11, 14, 13, 12], horizonte=5,
                   id_empresa="PRED-A", entidad="ventas", emitir=True)
        ev = c.cola.get(timeout=3)
        assert ev["tipo"] == "prediccion.generada" and str(ev["id_empresa"]) == "PRED-A"
        # aislamiento: otro tenant no habría recibido este evento (mismo mecanismo que test_realtime).
    finally:
        realtime.desregistrar(c)


def test_prediccion_service_forecast_ventas(db):
    """El motor unificado se expone en PredictionService (no es un motor paralelo)."""
    from src.services.prediccion import servicio
    r = servicio().forecast_ventas("PRED-EMPTY", horizonte=7)
    # Sin histórico → calidad insuficiente + heurística; NUNCA ML, y explicación honesta.
    assert r["es_ml"] is False and r["tipo"] == "heuristica"
    assert r["calidad_datos"] in ("DATA_QUALITY_INSUFFICIENT", "DATA_QUALITY_INVALID")
