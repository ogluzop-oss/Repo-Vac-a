"""
Panel central de INTELIGENCIA PREDICTIVA (Fase 8, Punto 7) — agrega KPIs explicables reutilizando los
servicios existentes (`stock.predecir`, `modelos.listar`, `forecasting`, `adaptadores`). NO recalcula ni
crea un motor/tabla nuevos: sólo compone lo que ya existe, aislado por tenant (`id_empresa`). Cada KPI lleva
su explicación (nunca un número sin significado). Honesto: la degradación/retraining se evalúan bajo demanda
(no hay estado persistente "degradado"), por lo que se reportan como "evaluables", no como un contador falso.
"""

import logging

logger = logging.getLogger("prediccion.panel")

_ETIQUETA = {"ml": "Machine Learning (Prophet)", "estadistica": "modelo estadístico",
             "heuristica": "estimación heurística"}


def kpis_predictivos(id_empresa) -> dict:
    """KPIs predictivos del tenant. Estructura estable para la UI (dashboard) y los informes."""
    from src.services.prediccion import stock as S, modelos as M, forecasting, adaptadores

    try:
        st = S.predecir(id_empresa)
    except Exception as e:
        logger.debug("stock.predecir: %s", e)
        st = {"activo": False, "predicciones": [], "sin_movimiento": [], "alta_rotacion": []}
    bajo = _safe(adaptadores.articulos_bajo_umbral, id_empresa)
    exceso = _safe(adaptadores.articulos_exceso, id_empresa)

    # Riesgo por artículo (criterio real de reposición): ALTO si stock < 40% del objetivo; MEDIO el resto.
    alto = sum(1 for a in bajo if a.get("objetivo") and a.get("stock_tienda", 0) < a["objetivo"] * 0.4)
    medio = len(bajo) - alto

    # Previsión agregada de ventas (motor real). Honesta con la calidad de datos.
    fc = forecasting.predecir_ventas(id_empresa, horizonte=7, emitir=False)
    suf = fc["n_observaciones"] >= forecasting.MIN_OBS
    pred = fc.get("prediccion") or []
    tendencia = ("creciente" if suf and len(pred) >= 2 and pred[-1] > pred[0]
                 else "decreciente" if suf and len(pred) >= 2 and pred[-1] < pred[0]
                 else "estable" if suf else "sin_datos")

    mods = M.listar(id_empresa, entidad="ventas", limite=500)
    por_estado = _contar(mods, "estado")
    por_tipo = _contar(mods, "tipo_modelo")
    maes = [float(m["mae"]) for m in mods if m.get("mae") is not None]
    wapes = [float(m["wape"]) for m in mods if m.get("wape") is not None]

    kpis = {
        "riesgo": {
            "articulos_riesgo_alto": alto,
            "articulos_riesgo_medio": medio,
            "articulos_sin_movimiento": len(st.get("sin_movimiento", [])),
            "articulos_sobrestock": len(exceso),
            "explicacion": "Artículos por debajo del stock objetivo (criterio real de reposición); "
                           "ALTO = stock < 40% del objetivo.",
        },
        "demanda": {
            "tendencia": tendencia,
            "prevision_7d": round(sum(pred), 2) if suf else None,
            "modelo": fc.get("modelo") if suf else None,
            "tipo": _ETIQUETA.get(fc.get("tipo"), fc.get("tipo")) if suf else None,
            "es_ml": fc.get("es_ml", False),
            "calidad_datos": fc.get("calidad_datos"),
            "n_observaciones": fc.get("n_observaciones"),
            "explicacion": "Previsión de ventas de 7 días con el motor real; sin datos suficientes se marca "
                           "'sin_datos' (nunca se inventa).",
        },
        "modelos": {
            "total": len(mods),
            "por_estado": por_estado,
            "activos": por_estado.get("ACTIVE", 0),
            "por_tipo": {_ETIQUETA.get(k, k): v for k, v in por_tipo.items()},
            "mae_medio": round(sum(maes) / len(maes), 4) if maes else None,
            "wape_medio": round(sum(wapes) / len(wapes), 4) if wapes else None,
            "degradacion": "evaluable bajo demanda (modelos.evaluar_degradacion); no hay contador persistente",
            "explicacion": "Modelos registrados por estado/tipo con sus métricas reales (MAE/WAPE).",
        },
        "acciones_recomendadas": _acciones(alto, len(bajo), suf, por_estado),
    }
    return {"id_empresa": id_empresa, "kpis": kpis}


def _acciones(alto, total_riesgo, suficiente, por_estado) -> list:
    acc = []
    if alto:
        acc.append(f"Revisar {alto} artículos de riesgo ALTO de rotura.")
    if total_riesgo:
        acc.append(f"Revisar reposición de {total_riesgo} artículos bajo objetivo.")
    if not suficiente:
        acc.append("Cargar más histórico de ventas: datos insuficientes para previsión fiable.")
    if not por_estado.get("ACTIVE"):
        acc.append("No hay modelo activo: validar/activar un candidato.")
    if not acc:
        acc.append("Sin acciones críticas: la operativa predictiva está estable.")
    return acc


def _contar(filas, campo) -> dict:
    out = {}
    for f in filas:
        k = f.get(campo)
        if k is not None:
            out[k] = out.get(k, 0) + 1
    return out


def _safe(fn, id_empresa):
    try:
        return fn(id_empresa) or []
    except Exception as e:
        logger.debug("%s: %s", getattr(fn, "__name__", fn), e)
        return []
