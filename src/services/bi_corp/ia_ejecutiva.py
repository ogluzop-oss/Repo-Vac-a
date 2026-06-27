"""
FASE J — IA ejecutiva. Genera automaticamente resumen ejecutivo, riesgos, oportunidades,
tendencias, desviaciones y recomendaciones a partir de KPIs/forecast/alertas. EXPLICABLE y
auditable: cada conclusion cita su metrica/fuente. Sin cajas negras.
"""

import logging
from src.db.conexion import log_auditoria
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("bi_corp.ia_ejecutiva")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def informe(*, id_empresa=None) -> dict:
    """Informe ejecutivo completo y explicable."""
    eid = _emp(id_empresa)
    from src.services.bi_corp import alertas, forecast_corp, kpis_corp

    kpis = {k["codigo"]: k for k in kpis_corp.cuadro(id_empresa=eid) if k.get("ok")}
    fc = forecast_corp.forecast_global(id_empresa=eid)
    alrt = alertas.detectar(id_empresa=eid)

    riesgos, oportunidades, tendencias, desviaciones, recomendaciones = [], [], [], [], []

    # Tendencias y riesgos desde el forecast (explicable: cita area/tendencia).
    for area, f in fc.items():
        if not f.get("ok"):
            continue
        tendencias.append({"area": area, "tendencia": f["tendencia"], "confianza": f["confianza"]})
        if f.get("riesgo") == "alto":
            riesgos.append({"area": area, "motivo": f"{area} con tendencia {f['tendencia']}",
                            "fuente": "forecast"})
        if area == "ventas" and f["tendencia"] == "subiendo":
            oportunidades.append({"area": "ventas", "motivo": "Ventas en tendencia positiva"})

    # Riesgos desde alertas (ya explicables).
    for a in alrt:
        if a["severidad"] in ("alta", "critica"):
            riesgos.append({"area": a["tipo"], "motivo": a["mensaje"], "fuente": "alertas"})

    # Desviaciones: presupuesto vs real (si hay presupuestos).
    try:
        from src.services.finanzas import presupuestos
        for p in presupuestos.listar(id_empresa=eid)[:3]:
            cmp = presupuestos.real_vs_presupuesto(p["id"], id_empresa=eid)
            d = cmp.get("resultado", {})
            if d.get("desviacion_pct") is not None and abs(d["desviacion_pct"]) >= 15:
                desviaciones.append({"presupuesto": p["codigo"], "desviacion_pct": d["desviacion_pct"],
                                     "fuente": "presupuestos"})
    except Exception:
        pass

    # Recomendaciones (derivadas, priorizadas).
    if any(r["area"] == "tesoreria" for r in riesgos):
        recomendaciones.append({"prioridad": 1, "accion": "Reforzar liquidez / revisar lineas de credito",
                                "motivo": "Riesgo de tesoreria detectado"})
    if any(a["tipo"] == "clientes_riesgo" for a in alrt):
        recomendaciones.append({"prioridad": 2, "accion": "Gestionar cobro de clientes de riesgo",
                                "motivo": "Clientes con riesgo de impago"})
    if any(a["tipo"] in ("rotura_stock", "exceso_stock") for a in alrt):
        recomendaciones.append({"prioridad": 3, "accion": "Ajustar politica de reaprovisionamiento",
                                "motivo": "Anomalias de stock"})

    resumen = _texto_resumen(kpis, riesgos, oportunidades)
    log_auditoria("bi_corp", "BI_IA_INFORME", "dw_hechos",
                  f"riesgos={len(riesgos)} recomendaciones={len(recomendaciones)}")
    return {"resumen": resumen, "kpis": kpis, "riesgos": riesgos, "oportunidades": oportunidades,
            "tendencias": tendencias, "desviaciones": desviaciones, "recomendaciones": recomendaciones,
            "explicable": True}


def _texto_resumen(kpis, riesgos, oportunidades):
    fact = kpis.get("facturacion", {}).get("valor", 0)
    ebitda = kpis.get("ebitda", {}).get("valor", 0)
    partes = [f"Facturacion {fact} €", f"EBITDA {ebitda} €"]
    if riesgos:
        partes.append(f"{len(riesgos)} riesgos detectados")
    if oportunidades:
        partes.append(f"{len(oportunidades)} oportunidades")
    return ". ".join(partes) + "."
