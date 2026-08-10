"""
Etapa C · Fase C3 — Panel Ejecutivo + Alertas Inteligentes (Áreas 5 y 6).

Capa de LECTURA transversal que COMPONE una fotografía ejecutiva reutilizando lo existente: KPIs
(`bi.kpis`), decisiones/recomendaciones/predicciones/alertas (Centro de Decisiones C1) y tendencias
(`bi.serie_historica`). No calcula métricas nuevas, no crea tablas ni motores, no modifica datos.
RBAC (`inteligencia.ver`). Multiempresa. Degradable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("inteligencia.panel")

FASE = "C3"

_PRIORIDAD_ORD = {"ALTA": 0, "MEDIA": 1, "BAJA": 2, "INFO": 3}


def _emp(id_empresa=None):
    from src.services import inteligencia
    return inteligencia._emp(id_empresa)


def _puede(usuario, id_empresa):
    from src.services import inteligencia
    return inteligencia._puede(usuario, "inteligencia.ver", id_empresa)


def _kpis(id_empresa, periodo):
    try:
        from src.services.bi import kpis
        return kpis.calcular_todos(periodo=periodo, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("kpis: %s", e)
        return {}


def alertas(id_empresa=None, *, usuario=None, prioridad=None, limite=100):
    """Alertas priorizadas = decisiones de tipo anomalía/riesgo (Centro de Decisiones), ordenadas por
    prioridad. Clasificadas por severidad. Solo lectura."""
    from src.services import inteligencia
    emp = _emp(id_empresa)
    if not _puede(usuario, emp):
        return []
    out = []
    for tipo in ("anomalia", "riesgo"):
        out += inteligencia.decisiones(emp, tipo=tipo, estado="propuesta", prioridad=prioridad,
                                       usuario=usuario, limite=limite)
    out.sort(key=lambda d: _PRIORIDAD_ORD.get(d.get("prioridad"), 9))
    return out[:limite]


def tendencia(codigo_kpi, *, id_empresa=None, usuario=None, periodo="mes"):
    """Serie histórica de un KPI (tendencia) reutilizando `bi.serie_historica`."""
    emp = _emp(id_empresa)
    if not _puede(usuario, emp):
        return []
    try:
        from src.services.bi import kpis
        return kpis.serie_historica(codigo_kpi, periodo=periodo, id_empresa=emp)
    except Exception as e:
        logger.debug("tendencia(%s): %s", codigo_kpi, e)
        return []


def panel(id_empresa=None, *, usuario=None, periodo="mes"):
    """Panel ejecutivo COMPUESTO: KPIs + resumen de decisiones + prioridades + alertas + predicciones
    + recomendaciones. Todo auto-generado a partir de lo existente. RBAC: `inteligencia.ver`."""
    from src.services import inteligencia
    emp = _emp(id_empresa)
    if not _puede(usuario, emp):
        return {"ok": False, "motivo": "no autorizado"}
    resumen = inteligencia.resumen(emp, usuario=usuario)
    prioridades = inteligencia.decisiones(emp, prioridad="ALTA", usuario=usuario, limite=20)
    recomendaciones = inteligencia.decisiones(emp, tipo="recomendacion", usuario=usuario, limite=20)
    predicciones = inteligencia.decisiones(emp, tipo="prediccion", usuario=usuario, limite=20)
    als = alertas(emp, usuario=usuario, limite=50)
    return {"ok": True, "periodo": periodo, "kpis": _kpis(emp, periodo),
            "resumen_decisiones": resumen, "prioridades": prioridades, "alertas": als,
            "recomendaciones": recomendaciones, "predicciones": predicciones,
            "totales": {"prioridades_alta": len(prioridades), "alertas": len(als),
                        "recomendaciones": len(recomendaciones), "predicciones": len(predicciones)}}


def descriptor() -> dict:
    return {"servicio": "inteligencia.panel", "etapa": "C", "fase": FASE, "estado": "implementado",
            "compone": ["bi.kpis", "bi.serie_historica", "inteligencia (Centro de Decisiones)"],
            "solo_lectura": True, "modifica_datos": False, "motor_nuevo": False}


__all__ = ["FASE", "panel", "alertas", "tendencia", "descriptor"]
