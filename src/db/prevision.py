"""
Previsión de demanda desacoplada (CMP.7).

Servicio reutilizable de previsión por artículo, SIN depender de la GUI (`main.py`). Usa
Facebook Prophet si está disponible y hay histórico suficiente; en caso contrario degrada a
una media móvil simple, y si tampoco hay datos devuelve 0 (el motor de reabastecimiento
sigue funcionando por punto de pedido). Best-effort: nunca lanza excepción.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("inventario.prevision")


def _ventas_diarias(codigo, id_empresa, dias_hist=180):
    """Histórico de unidades vendidas por día (desde venta_items/ventas)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DATE(v.fecha) d, COALESCE(SUM(vi.cantidad),0) q "
                "FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id "
                "WHERE vi.codigo_articulo=%s AND vi.id_empresa=%s "
                "AND v.fecha >= (CURDATE() - INTERVAL %s DAY) "
                "GROUP BY DATE(v.fecha) ORDER BY d",
                (codigo, id_empresa, int(dias_hist)))
            return [(r[0] if not isinstance(r, dict) else r["d"],
                     float(r[1] if not isinstance(r, dict) else r["q"])) for r in cur.fetchall()]
    except Exception as e:
        logger.warning("_ventas_diarias(%s): %s", codigo, e)
        return []


def prevision_demanda(codigo, dias, id_empresa=None) -> int:
    """Unidades previstas a consumir en los próximos `dias`. Best-effort (0 si no hay datos)."""
    if not codigo or not dias or int(dias) <= 0:
        return 0
    try:
        from src.db.empresa import empresa_actual_id
        id_empresa = id_empresa or empresa_actual_id()
    except Exception:
        pass
    serie = _ventas_diarias(codigo, id_empresa)
    if not serie:
        return 0
    # 1) Intento con Prophet (si está instalado y hay histórico suficiente).
    try:
        if len(serie) >= 30:
            from prophet import Prophet
            import pandas as pd
            df = pd.DataFrame({"ds": [s[0] for s in serie], "y": [s[1] for s in serie]})
            m = Prophet(weekly_seasonality=True, daily_seasonality=False,
                        yearly_seasonality=False)
            m.fit(df)
            fut = m.make_future_dataframe(periods=int(dias))
            pred = m.predict(fut).tail(int(dias))
            total = float(pred["yhat"].clip(lower=0).sum())
            return max(0, int(round(total)))
    except Exception as e:
        logger.info("Prophet no disponible para %s (%s); uso media móvil.", codigo, e)
    # 2) Degradación: media diaria * días.
    media = sum(q for _, q in serie) / max(1, len(serie))
    return max(0, int(round(media * int(dias))))
