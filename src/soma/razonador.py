"""
Razonamiento MULTIPASO de SOMA (Fase 5). Para consultas amplias/analíticas, SOMA consulta INTERNAMENTE
a varias fuentes (Especialistas IA vía AgentManager, Gemelo Digital, PredictionService) y SINTETIZA una
única respuesta. El usuario nunca ve el proceso interno. Reutiliza los servicios; no crea un segundo
razonador ni recalcula.
"""

import logging

logger = logging.getLogger("soma.razonador")

_ANALITICAS = ("analiza", "análisis", "analisis", "resumen", "resúmeme", "como estamos", "cómo estamos",
               "como va", "cómo va", "que deberia", "qué debería", "diagnostico", "diagnóstico",
               "situacion", "situación", "estado general", "vision general", "visión general",
               "que tal va", "qué tal va", "panorama")


def es_analitica(texto) -> bool:
    t = (texto or "").lower()
    if any(k in t for k in _ANALITICAS):
        return True
    # Fase 8: las consultas históricas ("¿cómo evolucionó…?") también son analíticas.
    try:
        from src.soma.empresa import historico
        return historico.es_historica(texto)
    except Exception:
        return False


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def sintetizar(texto, *, usuario=None, id_empresa=None, rol="ADMINISTRADOR") -> dict:
    """Consulta varias fuentes y devuelve una respuesta única {texto, fuentes, visual}."""
    emp = _emp(id_empresa)
    ctx = {"id_empresa": emp, "usuario": usuario, "rol": rol}

    # 0) Fase 8 — CONTEXTO HISTÓRICO: si preguntan por la evolución, responder con histórico + visual
    #    multimodal (reutiliza BI KPIs). Si hay dato, esta es la mejor respuesta.
    try:
        from src.soma.empresa import historico
        if historico.es_historica(texto):
            h = historico.responder(texto, id_empresa=emp)
            if h:
                return h
    except Exception as e:
        logger.debug("historico: %s", e)

    partes, fuentes, kpis = [], set(), []

    # 1) Estado global (Gemelo Digital) — visión operativa
    try:
        from src.services import gemelo
        g = gemelo.servicio().estado_empresa(emp)
        if g.get("resumen"):
            partes.append(g["resumen"])
            fuentes.add("Gemelo Digital")
        for dom, est in list((g.get("dominios") or {}).items())[:6]:
            kpis.append({"titulo": str(dom).capitalize(),
                         "valor": str(est.get("riesgo", "BAJO")),
                         "riesgo": str(est.get("riesgo", "BAJO"))})
    except Exception as e:
        logger.debug("gemelo: %s", e)

    # 2) Especialistas IA (coordinación automática de varios agentes)
    try:
        from src.services.agentes import manager
        r = manager().coordinar(texto, ctx)
        if r.get("texto"):
            partes.append(r["texto"])
            fuentes.update(r.get("fuentes", []))
    except Exception as e:
        logger.debug("agentes: %s", e)

    # 3) Predicción (riesgos relevantes)
    try:
        from src.services import prediccion
        rs = prediccion.servicio().riesgos(emp) or []
        if rs:
            top = "; ".join((x.get("texto") or x.get("descripcion") or "") for x in rs[:2] if x)
            if top:
                partes.append(f"Riesgos a vigilar: {top}.")
                fuentes.add("Predicción")
    except Exception as e:
        logger.debug("prediccion: %s", e)

    if not partes:
        return {}
    # Síntesis (única respuesta, sin exponer el proceso interno)
    texto_final = " ".join(dict.fromkeys(p.strip() for p in partes if p and p.strip()))
    return {"texto": texto_final, "fuentes": sorted(fuentes),
            "visual": ({"tipo": "kpis", "items": kpis} if kpis else None)}
