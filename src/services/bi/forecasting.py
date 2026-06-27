"""
Forecasting BI (FASE BI-10).

Reutiliza el patrón Prophet/media móvil del proyecto (igual que db/prevision.py) aplicado a la
serie histórica de cualquier KPI persistido, y expone atajos a los forecasters de dominio ya
existentes (ventas: predecir_ventas_semanales; liquidez: prevision_financiera). Horizontes
30/90/180/365. No introduce un motor nuevo.
"""

import logging

from src.services.bi import kpis as _K

logger = logging.getLogger("bi.forecasting")
HORIZONTES = (30, 90, 180, 365)


def _forecast_serie(puntos, dias) -> float:
    """Predice el valor agregado/medio del KPI a `dias` vista. Prophet si hay ≥30 puntos; si no,
    media móvil. `puntos`: lista de (fecha, valor)."""
    if not puntos:
        return 0.0
    valores = [float(v) for _, v in puntos]
    try:
        if len(puntos) >= 30:
            from prophet import Prophet
            import pandas as pd
            df = pd.DataFrame({"ds": [str(f) for f, _ in puntos], "y": valores})
            df["ds"] = pd.to_datetime(df["ds"])
            m = Prophet(weekly_seasonality=True, daily_seasonality=False, yearly_seasonality=False)
            m.fit(df)
            fut = m.make_future_dataframe(periods=int(dias))
            pred = m.predict(fut).tail(1)
            return round(float(pred["yhat"].iloc[0]), 2)
    except Exception as e:
        logger.info("Prophet no disponible (%s); uso media móvil.", e)
    # Media móvil de los últimos puntos como estimación.
    ventana = valores[-min(len(valores), 6):]
    return round(sum(ventana) / len(ventana), 2)


def forecast_kpi(codigo, *, horizontes=HORIZONTES, periodo="mes", id_empresa=None) -> dict:
    """Proyección de un KPI a cada horizonte a partir de su serie histórica persistida."""
    serie = _K.serie_historica(codigo, periodo=periodo, id_empresa=id_empresa)
    puntos = [(r["fecha"], r["valor"]) for r in serie]
    res = {"codigo": codigo, "historico": len(puntos),
           "proyecciones": [{"horizonte_dias": h, "valor_estimado": _forecast_serie(puntos, h)}
                            for h in horizontes]}
    _audit("BI_FORECAST_GENERADO", f"{codigo} ({len(puntos)} puntos)")
    return res


def forecast_liquidez(id_empresa=None) -> dict:
    """Atajo: reutiliza prevision_financiera (rama Tesorería)."""
    try:
        from src.services.tesoreria import prevision_financiera as PF
        r = PF.proyeccion_liquidez(id_empresa)
        _audit("BI_FORECAST_GENERADO", "liquidez")
        return r
    except Exception as e:
        logger.error("forecast_liquidez: %s", e)
        return {}


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("bi", accion, "bi_kpi_valores", detalle)
    except Exception:
        pass
