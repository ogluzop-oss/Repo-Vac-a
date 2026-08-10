"""
Integración de la IA predictiva con SOMA / Copiloto (Fase 6). SOMA responde preguntas de negocio usando el
PredictiveEngine REAL (`forecasting`), NO reglas paralelas. Distingue SIEMPRE heurística/estadística/ML y, si
no hay datos suficientes, lo dice claramente (nunca inventa cifras ni presenta heurística como IA/ML).
Aislado por tenant (`id_empresa`).
"""

import logging

logger = logging.getLogger("prediccion.consulta")

_ETIQUETA = {"ml": "Machine Learning (Prophet)", "estadistica": "modelo estadístico",
             "heuristica": "estimación heurística"}
_CLAVES_VENTAS = ("vender", "venta", "ventas", "demanda", "prevision", "previsión", "prever",
                  "forecast", "facturar", "facturación")
_CLAVES_RIESGO = ("riesgo de rotura", "rotura", "quedar sin", "quedarme sin", "reponer",
                  "reabastecer", "reabastecimiento", "falta de stock", "revisar para repo")
_CLAVES_MODELO = ("modelo", "reentren", "reentrenamiento", "degradad", "machine learning", "prophet")
_CLAVES_TENDENCIA = ("creciente", "crece", "crecimiento", "subiendo", "tendencia", "decreciente",
                     "cayendo", "bajando", "menor confianza", "menos confianza")


def responder(pregunta, id_empresa, *, horizonte=30) -> dict:
    """Punto ÚNICO de consulta predictiva conversacional (Fase 8). Enruta la pregunta al servicio real
    correspondiente (previsión / riesgo de rotura / tendencia / modelos). Devuelve siempre
    {aplicable, ...}; NUNCA calcula aquí (delega en forecasting/stock/modelos) ni inventa datos."""
    p = (pregunta or "").lower()
    # Orden: modelo → riesgo → tendencia → previsión (los específicos antes que el genérico de ventas).
    if any(k in p for k in _CLAVES_MODELO):
        return _resp_modelos(id_empresa)
    if any(k in p for k in _CLAVES_RIESGO):
        return _resp_riesgo(id_empresa)
    if any(k in p for k in _CLAVES_TENDENCIA):
        return _resp_tendencia(id_empresa, horizonte=horizonte)
    if any(k in p for k in _CLAVES_VENTAS):
        return prevision_ventas(id_empresa, horizonte=horizonte)
    return {"aplicable": False}


def _resp_riesgo(id_empresa) -> dict:
    """Artículos en riesgo de rotura (reutiliza el mismo criterio real que el Informe de Reposición)."""
    from src.services.prediccion import adaptadores
    bajo = adaptadores.articulos_bajo_umbral(id_empresa)
    if not bajo:
        return {"aplicable": True, "suficiente": True, "intent": "riesgo", "riesgo": [],
                "texto": "Actualmente no hay artículos en riesgo de rotura según el stock objetivo."}
    top = sorted(bajo, key=lambda a: a.get("faltan", 0), reverse=True)[:5]
    items = "; ".join(f"{a.get('nombre')} (faltan {a.get('faltan')})" for a in top)
    texto = (f"Hay {len(bajo)} artículos en riesgo de rotura. Los más críticos: {items}. "
             f"Se recomienda revisarlos para reposición (la decisión final es del usuario).")
    return {"aplicable": True, "suficiente": True, "intent": "riesgo", "n": len(bajo),
            "riesgo": top, "texto": texto}


def _resp_tendencia(id_empresa, *, horizonte=14) -> dict:
    """Tendencia de demanda (motor real) + artículos de mayor rotación. Honesto si faltan datos."""
    from src.services.prediccion import adaptadores, forecasting
    r = forecasting.predecir_ventas(id_empresa, horizonte=horizonte, emitir=False)
    if r["n_observaciones"] < forecasting.MIN_OBS:
        return {"aplicable": True, "suficiente": False, "intent": "tendencia",
                "texto": "No hay datos suficientes para responder con fiabilidad."}
    pred = r["prediccion"] or [0]
    tend = ("creciente" if pred[-1] > pred[0] else "decreciente" if pred[-1] < pred[0] else "estable")
    rot = adaptadores.rotacion_articulos(id_empresa, limite=5) or []
    tops = ", ".join(str(a.get("codigo")) for a in rot) if rot else "—"
    etiqueta = _ETIQUETA.get(r["tipo"], r["tipo"])
    texto = (f"La tendencia de demanda es {tend} según {r['modelo']} ({etiqueta}), "
             f"con {r['n_observaciones']} observaciones (confianza {r['confianza']}). "
             f"Artículos de mayor rotación: {tops}.")
    return {"aplicable": True, "suficiente": True, "intent": "tendencia", "tendencia": tend,
            "texto": texto, "detalle": r}


def _resp_modelos(id_empresa) -> dict:
    """Estado de los modelos predictivos del tenant (tipo/estado/métricas reales)."""
    from src.services.prediccion import modelos
    mods = modelos.listar(id_empresa, entidad="ventas", limite=100)
    if not mods:
        return {"aplicable": True, "suficiente": False, "intent": "modelos",
                "texto": "No hay modelos predictivos registrados todavía para esta empresa."}
    activos = [m for m in mods if m.get("estado") == "ACTIVE"]
    if activos:
        m = activos[0]
        etiqueta = _ETIQUETA.get(m.get("tipo_modelo"), m.get("tipo_modelo"))
        texto = (f"El modelo activo de ventas es {m.get('algoritmo')} ({etiqueta}), "
                 f"MAE {m.get('mae')}, WAPE {m.get('wape')}. Total de modelos registrados: {len(mods)}.")
    else:
        texto = (f"Hay {len(mods)} modelos registrados para esta empresa; ninguno activo actualmente. "
                 f"Puede activarse un candidato validado si mejora al anterior.")
    return {"aplicable": True, "suficiente": True, "intent": "modelos", "modelos": mods, "texto": texto}


def prevision_ventas(id_empresa, *, horizonte=30) -> dict:
    from src.services.prediccion import forecasting
    r = forecasting.predecir_ventas(id_empresa, horizonte=horizonte, emitir=False)
    n = r["n_observaciones"]
    if n < forecasting.MIN_OBS or r["calidad_datos"] in ("DATA_QUALITY_INSUFFICIENT", "DATA_QUALITY_INVALID"):
        return {"aplicable": True, "suficiente": False, "n_obs": n, "calidad": r["calidad_datos"],
                "texto": "No hay datos suficientes para generar una predicción fiable."}
    total = round(sum(r["prediccion"]), 2)
    etiqueta = _ETIQUETA.get(r["tipo"], r["tipo"])
    texto = (f"Según el histórico disponible, la previsión de ventas para los próximos {horizonte} días es "
             f"de aproximadamente {total}. Modelo utilizado: {r['modelo']} ({etiqueta}). "
             f"Histórico: {n} observaciones. Calidad de datos: {r['calidad_datos']}. "
             f"Confianza: {r['confianza']}.")
    return {"aplicable": True, "suficiente": True, "texto": texto, "modelo": r["modelo"],
            "tipo": r["tipo"], "es_ml": r["es_ml"], "confianza": r["confianza"],
            "calidad": r["calidad_datos"], "n_obs": n, "total_previsto": total, "detalle": r}


def resumen_ui(resultado: dict) -> dict:
    """Contrato COMPACTO para las tarjetas de previsión de la UI existente (Smart Stock, Reabastecimiento,
    Compras, Ventas). No crea UI: normaliza el resultado del motor para pintarlo. Etiqueta el origen con
    honestidad (nunca 'IA' si es heurística)."""
    from datetime import date
    tipo = resultado.get("tipo", "heuristica")
    return {
        "titulo": "PREVISIÓN DE DEMANDA",
        "horizonte_dias": resultado.get("horizonte"),
        "total_previsto": round(sum(resultado.get("prediccion") or [0]), 2),
        "modelo": resultado.get("modelo"),
        "tipo_modelo": _ETIQUETA.get(tipo, tipo),
        "es_ml": resultado.get("es_ml", False),
        "confianza": resultado.get("confianza"),
        "calidad_datos": resultado.get("calidad_datos"),
        "n_observaciones": resultado.get("n_observaciones"),
        "explicacion": resultado.get("explicacion"),
        "fecha_calculo": str(date.today()),
    }
