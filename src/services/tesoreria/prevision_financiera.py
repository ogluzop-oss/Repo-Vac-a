"""
Previsión financiera / liquidez futura (rama Tesorería, FASE 7).

Reutiliza el MISMO patrón de previsión que src/db/prevision.py (Facebook Prophet si está
disponible y hay histórico suficiente; si no, media móvil) — aquí aplicado a la serie diaria
del flujo NETO de tesorería. La liquidez estimada a cada horizonte combina:
    saldo disponible actual + vencimientos netos del periodo (determinista) + flujo operativo
    estimado (Prophet/media).
Genera alertas de tensión de caja cuando la liquidez proyectada cae por debajo del umbral.
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.tesoreria import posicion as _P

logger = logging.getLogger("prevision_financiera")

HORIZONTES = (30, 90, 180, 365)


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _serie_neta_diaria(id_empresa, dias_hist=180):
    """Serie (fecha, neto) del flujo de tesorería de los últimos `dias_hist` días."""
    desde = (_dt.date.today() - _dt.timedelta(days=int(dias_hist))).strftime("%Y-%m-%d")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT fecha AS d, COALESCE(SUM(importe),0) AS n FROM movimientos_tesoreria "
                        "WHERE id_empresa=%s AND fecha>=%s GROUP BY fecha ORDER BY fecha",
                        (id_empresa, desde))
            return [((r[0] if not isinstance(r, dict) else r["d"]),
                     float(r[1] if not isinstance(r, dict) else r["n"])) for r in cur.fetchall()]
    except Exception as e:
        logger.error("_serie_neta_diaria: %s", e)
        return []


def flujo_operativo_estimado(id_empresa, dias) -> float:
    """Estimación del flujo neto operativo de los próximos `dias` (Prophet o media móvil).
    Mismo enfoque que prevision.prevision_demanda, sobre el neto diario de tesorería."""
    id_empresa = _emp(id_empresa)
    serie = _serie_neta_diaria(id_empresa)
    if not serie:
        return 0.0
    try:
        if len(serie) >= 30:
            from prophet import Prophet
            import pandas as pd
            df = pd.DataFrame({"ds": [s[0] for s in serie], "y": [s[1] for s in serie]})
            m = Prophet(weekly_seasonality=True, daily_seasonality=False, yearly_seasonality=False)
            m.fit(df)
            fut = m.make_future_dataframe(periods=int(dias))
            pred = m.predict(fut).tail(int(dias))
            return round(float(pred["yhat"].sum()), 2)
    except Exception as e:
        logger.info("Prophet no disponible (%s); uso media móvil.", e)
    media = sum(n for _, n in serie) / max(1, len(serie))
    return round(media * int(dias), 2)


def proyeccion_liquidez(id_empresa=None, horizontes=HORIZONTES, umbral=0.0) -> dict:
    """Liquidez estimada a cada horizonte (30/90/180/365 por defecto), con detección de tensión.

    liquidez = disponible + (por_cobrar_h − comprometido_h) + flujo_operativo_estimado_h
    """
    id_empresa = _emp(id_empresa)
    pos = _P.posicion(id_empresa)
    disponible = pos["disponible"]
    proyecciones = []
    for h in horizontes:
        hasta = (_dt.date.today() + _dt.timedelta(days=int(h))).strftime("%Y-%m-%d")
        cobrar = _P._pendiente(id_empresa, "COBRO", hasta)
        pagar = _P._pendiente(id_empresa, "PAGO", hasta)
        operativo = flujo_operativo_estimado(id_empresa, h)
        liquidez = round(disponible + (cobrar - pagar) + operativo, 2)
        proyecciones.append({
            "horizonte_dias": int(h),
            "fecha": hasta,
            "disponible_inicial": disponible,
            "por_cobrar": cobrar,
            "comprometido": pagar,
            "flujo_operativo_estimado": operativo,
            "liquidez_estimada": liquidez,
            "tension": liquidez < umbral,
        })
    return {"id_empresa": id_empresa, "disponible_actual": disponible,
            "umbral": umbral, "proyecciones": proyecciones}


def alertas_liquidez(id_empresa=None, umbral=0.0) -> list:
    """Lista de horizontes en tensión (liquidez estimada < umbral)."""
    proy = proyeccion_liquidez(id_empresa, umbral=umbral)
    return [{"horizonte_dias": p["horizonte_dias"], "fecha": p["fecha"],
             "liquidez_estimada": p["liquidez_estimada"]}
            for p in proy["proyecciones"] if p["tension"]]
