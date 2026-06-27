"""
FASE H — Dashboard financiero ejecutivo. Agrega (solo lectura) tesoreria + presupuestos + forecast
+ financiacion + riesgo + credito + ratios + alertas + anomalias IA. Multiempresa/tienda/almacen.
FASE G — Jobs de Scheduler (ratios/forecast/riesgo/anomalias) registrables (opt-in).
"""

import logging
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("finanzas.dashboard")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def panel(*, id_empresa=None, anio=None) -> dict:
    eid = _emp(id_empresa)
    out = {}
    # Tesoreria / posicion
    try:
        from src.services.tesoreria import posicion
        out["tesoreria"] = posicion.posicion(id_empresa=eid)
    except Exception as e:
        logger.debug("tesoreria: %s", e); out["tesoreria"] = {}
    # Forecast liquidez (reutiliza el existente)
    try:
        from src.services.finanzas import ia
        out["forecast_liquidez"] = ia.prediccion_liquidez(id_empresa=eid)
        out["riesgo_tesoreria"] = ia.riesgo_tesoreria(id_empresa=eid)
        out["anomalias_ia"] = ia.deteccion_anomalias(id_empresa=eid)[:10]
        out["recomendaciones"] = ia.recomendaciones(id_empresa=eid)
    except Exception as e:
        logger.debug("ia: %s", e)
    # Ratios
    try:
        from src.services.finanzas import ratios
        out["ratios"] = ratios.calcular(anio=anio, id_empresa=eid)
    except Exception as e:
        logger.debug("ratios: %s", e); out["ratios"] = {}
    # Financiacion / deuda
    try:
        from src.services.finanzas import financiacion
        out["deuda"] = financiacion.deuda_viva(id_empresa=eid)
    except Exception as e:
        logger.debug("deuda: %s", e); out["deuda"] = {}
    # Credito (alertas abiertas)
    try:
        from src.services.finanzas import credito
        out["alertas_credito"] = credito.listar_alertas(id_empresa=eid)[:20]
    except Exception as e:
        logger.debug("credito: %s", e); out["alertas_credito"] = []
    # Presupuestos del ejercicio
    try:
        from src.services.finanzas import presupuestos
        pptos = presupuestos.listar(ejercicio=anio, id_empresa=eid)
        out["presupuestos"] = [{"id": p["id"], "codigo": p["codigo"],
                                "comparativa": presupuestos.real_vs_presupuesto(p["id"], id_empresa=eid)}
                               for p in pptos[:5]]
    except Exception as e:
        logger.debug("presupuestos: %s", e); out["presupuestos"] = []
    return out


# ── FASE G · Jobs Scheduler ───────────────────────────────────────────────────
def _job_ratios(id_empresa):
    from src.services.finanzas import ratios
    ratios.registrar_en_bi(id_empresa=id_empresa)
    return "ratios_bi_ok"


def _job_riesgo_credito(id_empresa):
    from src.services.finanzas import ia
    return f"impagos={len(ia.prediccion_impagos(id_empresa=id_empresa))}"


def _job_anomalias(id_empresa):
    from src.services.finanzas import ia
    return f"anomalias={len(ia.deteccion_anomalias(id_empresa=id_empresa))}"


def registrar_jobs_finanzas(id_empresa=None):
    """Registra los jobs financieros en el Scheduler (idempotente, opt-in)."""
    from src.services import scheduler
    scheduler.registrar("fin_ratios", _job_ratios)
    scheduler.registrar("fin_riesgo_credito", _job_riesgo_credito)
    scheduler.registrar("fin_anomalias", _job_anomalias)
    scheduler.registrar_job("fin_ratios", intervalo_horas=24, descripcion="Ratios financieros a BI",
                            id_empresa=id_empresa)
    scheduler.registrar_job("fin_riesgo_credito", intervalo_horas=24, descripcion="Riesgo de credito/impagos",
                            id_empresa=id_empresa)
    scheduler.registrar_job("fin_anomalias", intervalo_horas=24, descripcion="Anomalias financieras",
                            id_empresa=id_empresa)
