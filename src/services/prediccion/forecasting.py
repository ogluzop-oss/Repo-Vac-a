"""
Motor de forecasting UNIFICADO (Fase 5) — evolución del motor predictivo existente, NO un sistema paralelo.

Reutiliza: las series históricas reales (`prediccion.adaptadores` / `ia.adaptadores`), el etiquetado de
origen (`prediccion.heuristicas.motor_activo`), el Event Bus existente (`services.eventbus.publish`) y el
aislamiento por tenant (`id_empresa`). Añade, con matemática real (sin mocks): informe de CALIDAD DE DATOS,
SELECCIÓN AUTOMÁTICA de modelo, BACKTESTING temporal con métricas (MAE/RMSE/WAPE), integración REAL de
Prophet cuando los datos lo permiten (degradable), INTERVALO DE CONFIANZA, EXPLICABILIDAD y metadatos de
modelo versionados. Distingue SIEMPRE: heurística · estadística · ML (Prophet). Nunca presenta una
heurística como IA/ML.

Umbrales (nº de observaciones): <14 media móvil · 14–59 tendencia lineal · ≥60 (con estacionalidad y
Prophet disponible) Prophet. Sin datos suficientes o inválidos → heurística/estadística; NUNCA Prophet.
"""

import hashlib
import logging
import math
from datetime import date, timedelta

logger = logging.getLogger("prediccion.forecasting")

MIN_OBS = 7            # mínimo absoluto para cualquier previsión
UMBRAL_LINEAL = 14
UMBRAL_PROPHET = 60

# ── Calidad de datos ──────────────────────────────────────────────────────────
CAL_GOOD = "DATA_QUALITY_GOOD"
CAL_WARNING = "DATA_QUALITY_WARNING"
CAL_INSUFFICIENT = "DATA_QUALITY_INSUFFICIENT"
CAL_INVALID = "DATA_QUALITY_INVALID"


def calidad_datos(valores) -> dict:
    """Informe de calidad de la serie (reutilizable). No usa datos de otros tenants."""
    n = len(valores)
    motivos = []
    if n < MIN_OBS:
        return {"estado": CAL_INSUFFICIENT, "n": n, "motivos": [f"solo {n} observaciones (<{MIN_OBS})"]}
    try:
        vals = [float(v) for v in valores]
    except (TypeError, ValueError):
        return {"estado": CAL_INVALID, "n": n, "motivos": ["valores no numéricos"]}
    negativos = sum(1 for v in vals if v < 0)
    if negativos:
        motivos.append(f"{negativos} valores negativos")
    media = sum(vals) / n
    var = sum((v - media) ** 2 for v in vals) / n
    desv = math.sqrt(var)
    if desv == 0:
        motivos.append("serie constante (sin variabilidad)")
    # outliers extremos (> 5σ)
    if desv > 0:
        outliers = sum(1 for v in vals if abs(v - media) > 5 * desv)
        if outliers:
            motivos.append(f"{outliers} outliers extremos (>5σ)")
    estado = CAL_GOOD if not motivos else CAL_WARNING
    if negativos and estado == CAL_WARNING and negativos > n * 0.2:
        estado = CAL_INVALID
    return {"estado": estado, "n": n, "media": round(media, 4), "desviacion": round(desv, 4),
            "motivos": motivos}


# ── Modelos (per-periodo) ─────────────────────────────────────────────────────
def _media_movil(vals, pasos, ventana=7):
    if not vals:
        return [0.0] * pasos
    w = min(ventana, len(vals))
    base = sum(vals[-w:]) / w
    return [base] * pasos


def _tendencia_lineal(vals, pasos):
    n = len(vals)
    if n < 2:
        return _media_movil(vals, pasos)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(vals) / n
    sxx = sum((x - mx) ** 2 for x in xs) or 1.0
    sxy = sum((xs[i] - mx) * (vals[i] - my) for i in range(n))
    b = sxy / sxx
    a = my - b * mx
    return [a + b * (n + k) for k in range(pasos)]


def _prophet(fechas, vals, pasos):
    """Prophet REAL (degradable). Devuelve (forecast, lower, upper) o None si no aplica/instalado/falla."""
    try:
        import pandas as pd
        from prophet import Prophet
        logging.getLogger("prophet").setLevel(logging.ERROR)
        logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
    except Exception as e:
        logger.debug("Prophet no disponible: %s", e)
        return None
    try:
        df = pd.DataFrame({"ds": pd.to_datetime(fechas), "y": [float(v) for v in vals]})
        semanal = len(vals) >= 14
        anual = len(vals) >= 365
        m = Prophet(weekly_seasonality=semanal, yearly_seasonality=anual, daily_seasonality=False,
                    interval_width=0.8)
        m.fit(df)
        fut = m.make_future_dataframe(periods=pasos, freq="D")
        fc = m.predict(fut).tail(pasos)
        return (fc["yhat"].tolist(), fc["yhat_lower"].tolist(), fc["yhat_upper"].tolist())
    except Exception as e:
        logger.debug("Prophet fit falló (fallback): %s", e)
        return None


def _seleccionar(n, calidad, prophet_ok) -> str:
    if calidad in (CAL_INSUFFICIENT, CAL_INVALID) or n < UMBRAL_LINEAL:
        return "media_movil"
    if n < UMBRAL_PROPHET or not prophet_ok:
        return "tendencia_lineal"
    return "prophet"


# ── Backtesting (validación temporal, sin usar el futuro) ─────────────────────
def _backtest(vals, algoritmo, fechas=None) -> dict:
    """Train/test temporal: entrena con el histórico menos el holdout y compara con el holdout real."""
    n = len(vals)
    h = max(1, min(n // 5, 14))
    train, test = vals[:-h], vals[-h:]
    if len(train) < MIN_OBS:
        return {}
    if algoritmo == "media_movil":
        pred = _media_movil(train, h)
    elif algoritmo == "tendencia_lineal":
        pred = _tendencia_lineal(train, h)
    elif algoritmo == "prophet" and fechas:
        pr = _prophet(fechas[:-h], train, h)
        pred = pr[0] if pr else _tendencia_lineal(train, h)
    else:
        pred = _tendencia_lineal(train, h)
    errs = [abs(test[i] - pred[i]) for i in range(h)]
    mae = sum(errs) / h
    rmse = math.sqrt(sum(e * e for e in errs) / h)
    suma = sum(abs(t) for t in test)
    wape = (sum(errs) / suma) if suma else None
    return {"holdout": h, "mae": round(mae, 4), "rmse": round(rmse, 4),
            "wape": round(wape, 4) if wape is not None else None}


# ── Motor unificado ───────────────────────────────────────────────────────────
def _model_id(id_empresa, entidad, algoritmo) -> str:
    from datetime import datetime
    sem = f"{id_empresa}|{entidad}|{algoritmo}|{datetime.now():%Y%m%d%H%M%S}"
    return "mdl_" + hashlib.sha256(sem.encode()).hexdigest()[:16]


def _explicacion(algoritmo, tipo, n, calidad, metricas, seasonal) -> str:
    if algoritmo == "prophet":
        est = "semanal" + (" y anual" if seasonal.get("anual") else "") if seasonal.get("semanal") else "no detectada"
        return (f"Predicción basada en Prophet (ML de series temporales). Histórico: {n} observaciones. "
                f"Calidad: {calidad}. Estacionalidad: {est}. MAE validado: {metricas.get('mae', '—')}. ")
    if algoritmo == "tendencia_lineal":
        return (f"Predicción estadística (tendencia lineal). Histórico: {n} observaciones. "
                f"Datos insuficientes para un modelo ML de series (mín. {UMBRAL_PROPHET}). "
                f"Calidad: {calidad}. MAE validado: {metricas.get('mae', '—')}. ")
    return (f"Predicción heurística (media móvil). Histórico: {n} observaciones. "
            f"Datos insuficientes para modelo estadístico/ML. Calidad: {calidad}. ")


def forecast(valores, *, fechas=None, horizonte=7, id_empresa=None, entidad="ventas",
             emitir=True, persistir=False) -> dict:
    """Previsión unificada de UNA serie (aislada por tenant). Devuelve un resultado rico y HONESTO sobre el
    origen (heurística/estadística/ML). Publica `prediccion.generada` en el Event Bus (→ SSE)."""
    vals = [float(v) for v in valores] if valores else []
    cal = calidad_datos(vals)
    n = cal["n"]
    prophet_ok = n >= UMBRAL_PROPHET and _prophet is not None
    algoritmo = _seleccionar(n, cal["estado"], prophet_ok)

    # Backtesting (métricas de validación reales).
    metricas = _backtest(vals, algoritmo, fechas) if n >= MIN_OBS + 1 else {}

    seasonal = {"semanal": n >= 14, "anual": n >= 365}
    fc = lower = upper = None
    tipo = "heuristica"
    if algoritmo == "prophet":
        pr = _prophet(fechas, vals, horizonte)
        if pr:
            fc, lower, upper = pr
            tipo = "ml"
        else:
            algoritmo = "tendencia_lineal"     # fallback honesto: Prophet no aplicable/falló
    if fc is None:
        if algoritmo == "tendencia_lineal":
            fc = _tendencia_lineal(vals, horizonte); tipo = "estadistica"
        else:
            fc = _media_movil(vals, horizonte); tipo = "heuristica"
        # Intervalo de confianza ≈ ±1.28σ de los residuos in-sample (80%).
        desv = cal.get("desviacion", 0) or 0
        margen = 1.28 * desv
        lower = [max(0.0, y - margen) for y in fc]
        upper = [y + margen for y in fc]

    fc = [round(max(0.0, y), 4) for y in fc]
    lower = [round(max(0.0, y), 4) for y in (lower or fc)]
    upper = [round(y, 4) for y in (upper or fc)]
    modelo_no_aplicable = (n < UMBRAL_PROPHET)

    resultado = {
        "id_empresa": id_empresa, "entidad": entidad, "horizonte": horizonte, "granularidad": "dia",
        "modelo": algoritmo, "tipo": tipo, "es_ml": tipo == "ml",
        "model_id": _model_id(id_empresa, entidad, algoritmo), "version": 1,
        "estado_modelo": "VALIDATED" if metricas else "ACTIVE",
        "n_observaciones": n, "calidad_datos": cal["estado"],
        "prediccion": fc, "intervalo_inferior": lower, "intervalo_superior": upper,
        "metricas": metricas, "confianza": _confianza(cal["estado"], metricas, algoritmo),
        "explicacion": _explicacion(algoritmo, tipo, n, cal["estado"], metricas, seasonal),
        "model_not_applicable": {"prophet": modelo_no_aplicable, "min_requerido": UMBRAL_PROPHET}
                                if algoritmo != "prophet" else None,
    }
    # Versionado PERSISTENTE (Fase 6): registra el modelo entrenado con sus métricas reales. Opt-in
    # (`persistir=True`) para no escribir en cálculos ad-hoc; degradable (no rompe la previsión si falla).
    if persistir and id_empresa:
        try:
            from src.services.prediccion import modelos
            reg = modelos.registrar(resultado["model_id"], id_empresa=id_empresa, entidad=entidad,
                                    algoritmo=algoritmo, tipo_modelo=tipo, n_observaciones=n,
                                    metricas=metricas, calidad_datos=cal["estado"], estado="VALIDATED")
            resultado["hash_integridad"] = reg.get("hash_integridad")
        except Exception as e:
            logger.debug("persistir modelo: %s", e)
    if emitir and id_empresa:
        try:
            from src.services.eventbus import publish
            publish("prediccion.generada", id_empresa=id_empresa,
                    payload={"entidad": entidad, "modelo": algoritmo, "tipo": tipo,
                             "model_id": resultado["model_id"], "version": 1, "horizonte": horizonte})
        except Exception as e:
            logger.debug("emitir prediccion.generada: %s", e)
    return resultado


def _confianza(calidad, metricas, algoritmo) -> str:
    if calidad in (CAL_INSUFFICIENT, CAL_INVALID):
        return "baja"
    if algoritmo == "prophet" and calidad == CAL_GOOD:
        return "alta"
    if metricas.get("wape") is not None and metricas["wape"] < 0.2:
        return "alta"
    return "media"


def predecir_ventas(id_empresa=None, *, horizonte=7, dias_hist=180, emitir=True) -> dict:
    """Previsión de ventas de un tenant a partir de su serie diaria REAL (`adaptadores.ventas_por_dia`).
    Aislada por `id_empresa`. Nunca mezcla datos de otros tenants."""
    from src.services.prediccion import adaptadores
    try:
        serie = adaptadores.ventas_por_dia(id_empresa, dias=dias_hist)
    except Exception as e:
        logger.debug("ventas_por_dia: %s", e)
        serie = []
    # Completa con el HISTÓRICO IMPORTADO (ventas_historicas) las fechas que la serie real no cubre — así el
    # forecasting aprovecha el pasado migrado SIN alterar los datos operativos reales (fill-gaps, no suma).
    try:
        hist = adaptadores.ventas_hist_por_dia(id_empresa, dias=dias_hist)
    except Exception as e:
        logger.debug("ventas_hist_por_dia: %s", e)
        hist = []
    if hist:
        por_fecha = {str(r.get("d")): float(r.get("total") or 0) for r in serie}
        for r in hist:
            d = str(r.get("d"))
            por_fecha.setdefault(d, float(r.get("total") or 0))
        serie = [{"d": d, "total": por_fecha[d]} for d in sorted(por_fecha)]
    fechas = [str(r.get("d")) for r in serie]
    valores = [float(r.get("total") or 0) for r in serie]
    return forecast(valores, fechas=fechas, horizonte=horizonte, id_empresa=id_empresa,
                    entidad="ventas", emitir=emitir, persistir=True)
