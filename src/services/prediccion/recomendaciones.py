"""
Recomendaciones de reposición asistida (Fase 8, Puntos 2 y 4) — para Compras e Informes. REUTILIZA el criterio
real de reposición (`adaptadores.articulos_bajo_umbral`, el mismo del Informe de Reposición) + la previsión
del motor real (`forecasting`) como CONTEXTO de empresa. NO genera pedidos: sólo asiste; la decisión es humana.
Aislado por tenant. Honesto: la previsión es agregada de empresa (contexto), no un modelo por SKU (🟡 futuro).
"""

import logging

logger = logging.getLogger("prediccion.recomendaciones")

_RECO = {"ALTO": "Reposición recomendada", "MEDIO": "Revisar stock",
         "BAJO": "Cobertura suficiente", "INSUFICIENTE": "Sin datos suficientes"}


def recomendaciones_reposicion(id_empresa, *, limite=20) -> dict:
    """Lista de artículos a revisar para reposición con contexto predictivo (riesgo, tendencia, confianza)."""
    from src.services.prediccion import adaptadores, forecasting

    bajo = _safe(adaptadores.articulos_bajo_umbral, id_empresa)
    fc = forecasting.predecir_ventas(id_empresa, horizonte=7, emitir=False)
    suf = fc["n_observaciones"] >= forecasting.MIN_OBS
    pred = fc.get("prediccion") or []
    dem_empresa = round(sum(pred) / len(pred), 2) if (suf and pred) else None
    tendencia = ("creciente" if suf and len(pred) >= 2 and pred[-1] > pred[0]
                 else "decreciente" if suf and len(pred) >= 2 and pred[-1] < pred[0] else "estable")

    out = []
    for a in sorted(bajo, key=lambda x: x.get("faltan", 0), reverse=True)[:limite]:
        tie, esp = a.get("stock_tienda", 0), a.get("objetivo", 0)
        # Riesgo por artículo con su PROPIA cobertura (no la demanda agregada): honesto por SKU.
        nivel = "ALTO" if (esp and tie < esp * 0.4) else "MEDIO"
        out.append({
            "codigo": a.get("codigo"), "nombre": a.get("nombre"),
            "stock_actual": tie, "objetivo": esp, "faltan": a.get("faltan"),
            "demanda_prevista_empresa": dem_empresa,           # contexto agregado (no por SKU)
            "riesgo": nivel, "tendencia": tendencia if suf else "sin_datos",
            "confianza": fc.get("confianza") if suf else "baja",
            "calidad_datos": fc.get("calidad_datos"),
            "modelo": fc.get("modelo") if suf else None,
            "recomendacion": _RECO[nivel] if suf else _RECO["MEDIO"],
        })
    return {"id_empresa": id_empresa, "n_riesgo": len(bajo), "recomendaciones": out,
            "modelo": fc.get("modelo"), "tipo": fc.get("tipo"), "suficiente": suf}


def _safe(fn, id_empresa):
    try:
        return fn(id_empresa) or []
    except Exception as e:
        logger.debug("%s: %s", getattr(fn, "__name__", fn), e)
        return []
