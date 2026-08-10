"""
CONTEXTO HISTÓRICO (Fase 8). Cuando el usuario pregunta "¿cómo evolucionó esto?", SOMA responde con
histórico, no solo con datos actuales. Reutiliza la serie histórica de KPIs del BI existente
(`services.bi.kpis.serie_historica`) — no recalcula ni crea un almacén nuevo — y la presenta con las
visualizaciones multimodales ([[multimodal]]). Best-effort: si no hay serie, lo dice con naturalidad.
"""

import logging

from src.soma.empresa import multimodal

logger = logging.getLogger("soma.empresa.historico")

# Dominio/tema del usuario → código de KPI del BI (el primero que exista).
_KPI = {
    "ventas": ["ventas_total", "ventas_importe", "ingresos"],
    "stock": ["stock_valor", "stock_unidades", "inventario_valor"],
    "mermas": ["mermas_total", "mermas_importe"],
    "clientes": ["clientes_activos", "clientes_total"],
    "tesoreria": ["tesoreria_saldo", "liquidez"],
    "compras": ["compras_total", "compras_importe"],
}

_TEMAS = {
    "venta": "ventas", "ventas": "ventas", "stock": "stock", "inventario": "stock",
    "merma": "mermas", "mermas": "mermas", "cliente": "clientes", "clientes": "clientes",
    "tesorer": "tesoreria", "liquidez": "tesoreria", "caja": "tesoreria",
    "compra": "compras", "compras": "compras", "kpi": "ventas",
}

_HISTORICAS = ("evolucion", "evolución", "evolucionó", "evoluciono", "histórico", "historico",
               "tendencia", "respecto a", "comparado con", "comparativa", "como ha ido",
               "cómo ha ido", "va mejorando", "ha mejorado", "ultimos meses", "últimos meses",
               "mes a mes", "mensual")


def es_historica(texto) -> bool:
    t = (texto or "").lower()
    return any(k in t for k in _HISTORICAS)


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def _serie(tema, id_empresa):
    try:
        from src.services.bi import kpis
        for cod in _KPI.get(tema, []):
            s = kpis.serie_historica(cod, id_empresa=id_empresa, limite=24) or []
            if s:
                return cod, [{"fecha": p.get("fecha"), "valor": p.get("valor")} for p in s]
    except Exception as e:
        logger.debug("serie: %s", e)
    return None, []


def comparar(tema, *, id_empresa=None) -> dict:
    """{actual, anterior, variacion, variacion_pct, tendencia, serie}. tendencia ∈ sube|baja|estable."""
    emp = _emp(id_empresa)
    _cod, serie = _serie(tema, emp)
    if len(serie) < 2:
        return {}
    actual = float(serie[-1]["valor"] or 0)
    anterior = float(serie[-2]["valor"] or 0)
    var = round(actual - anterior, 2)
    pct = round((var / anterior * 100), 2) if anterior else None
    tend = "sube" if var > 0 else "baja" if var < 0 else "estable"
    return {"actual": actual, "anterior": anterior, "variacion": var, "variacion_pct": pct,
            "tendencia": tend, "serie": serie}


def _tema_de(texto) -> str:
    t = (texto or "").lower()
    for k, tema in _TEMAS.items():
        if k in t:
            return tema
    return "ventas"


def responder(texto, *, id_empresa=None) -> dict:
    """Responde una consulta histórica con texto + visual multimodal + fuentes. {} si no hay dato."""
    emp = _emp(id_empresa)
    tema = _tema_de(texto)
    d = comparar(tema, id_empresa=emp)
    if not d:
        return {}
    signo = {"sube": "ha mejorado", "baja": "ha empeorado", "estable": "se ha mantenido"}[d["tendencia"]]
    pct = f" ({d['variacion_pct']:+.1f}%)" if d.get("variacion_pct") is not None else ""
    spark = multimodal.sparkline([p["valor"] for p in d["serie"]])
    txt = (f"La evolución de {tema} {signo}: de {d['anterior']} a {d['actual']}{pct}. "
           f"Tendencia reciente: {spark}")
    return {"texto": txt, "fuentes": ["Histórico BI"],
            "visual": multimodal.evolucion(tema.capitalize(), d["serie"])}
