"""
Riesgo de rotura de stock (Fase 7) — combina la DEMANDA PREVISTA del motor real (`forecasting`) con el
stock actual, el mínimo, los pedidos pendientes y el lead time. Devuelve BAJO/MEDIO/ALTO o "datos
insuficientes" (nunca inventa). Aislado por tenant. Reutiliza el forecasting existente (no duplica).
"""

import logging

logger = logging.getLogger("prediccion.riesgo_rotura")

BAJO, MEDIO, ALTO, INSUF = "BAJO", "MEDIO", "ALTO", "INSUFICIENTE"


def evaluar(*, stock_actual, demanda_diaria, stock_minimo=0, pendientes=0, lead_time=7) -> dict:
    """Función PURA (testable): nivel de riesgo a partir de las magnitudes. Sin acceso a datos.
    - ALTO  : el stock disponible (actual+pendientes) no cubre la demanda durante el lead time.
    - MEDIO : cobertura < 1,5× lead time, o el stock cae por debajo del mínimo.
    - BAJO  : cobertura holgada."""
    if demanda_diaria is None or demanda_diaria <= 0:
        return {"nivel": INSUF, "motivo": "sin demanda prevista fiable",
                "recomendacion": "Datos insuficientes para calcular el riesgo."}
    disponible = float(stock_actual or 0) + float(pendientes or 0)
    cobertura_dias = round(float(stock_actual or 0) / demanda_diaria, 1)
    necesidad_lead = demanda_diaria * float(lead_time or 0)
    if disponible < necesidad_lead:
        nivel, reco = ALTO, "Riesgo alto: reponer con urgencia (no cubre el plazo de suministro)."
    elif cobertura_dias < float(lead_time or 0) * 1.5 or float(stock_actual or 0) <= float(stock_minimo or 0):
        nivel, reco = MEDIO, "Riesgo medio: se recomienda revisar el reabastecimiento."
    else:
        nivel, reco = BAJO, "Riesgo bajo: cobertura suficiente."
    return {"nivel": nivel, "cobertura_dias": cobertura_dias, "demanda_diaria": round(demanda_diaria, 2),
            "necesidad_lead_time": round(necesidad_lead, 2), "disponible": round(disponible, 2),
            "recomendacion": reco}


def riesgo_articulo(id_empresa, codigo, *, stock_minimo=0, pendientes=0, lead_time=7, horizonte=30) -> dict:
    """Riesgo de rotura REAL de un artículo: demanda diaria prevista (forecasting) + stock actual (BD)."""
    from src.services.prediccion import forecasting
    # Demanda diaria prevista = media de la previsión del horizonte (motor real, por tenant).
    try:
        r = forecasting.predecir_ventas(id_empresa, horizonte=horizonte, emitir=False)
        pred = r.get("prediccion") or []
        demanda_diaria = (sum(pred) / len(pred)) if pred else 0
        calidad = r.get("calidad_datos")
        if r.get("n_observaciones", 0) < forecasting.MIN_OBS:
            return {"nivel": INSUF, "codigo": codigo, "calidad": calidad,
                    "recomendacion": "Datos insuficientes para calcular el riesgo."}
    except Exception as e:
        logger.debug("riesgo_articulo forecast: %s", e)
        return {"nivel": INSUF, "codigo": codigo, "recomendacion": "Datos insuficientes."}
    stock_actual = _stock_actual(id_empresa, codigo)
    res = evaluar(stock_actual=stock_actual, demanda_diaria=demanda_diaria,
                  stock_minimo=stock_minimo, pendientes=pendientes, lead_time=lead_time)
    res.update({"codigo": codigo, "stock_actual": stock_actual, "calidad": calidad})
    return res


def _stock_actual(id_empresa, codigo) -> float:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(Stock_total, Stock_tienda, 0) FROM articulos "
                        "WHERE codigo=%s AND id_empresa<=>%s LIMIT 1", (codigo, id_empresa))
            r = cur.fetchone()
            if not r:
                return 0.0
            return float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception as e:
        logger.debug("_stock_actual: %s", e)
        return 0.0
