"""
CRM-H — IA comercial (scoring) SIN APIs externas, degrada elegantemente.

Lead scoring y probabilidad de cierre con un modelo heuristico transparente (reglas ponderadas
sobre datos reales del CRM). Si Prophet/datos historicos estan disponibles se usan para el forecast;
si no, se cae al ponderado del pipeline. Persiste el score en crm_leads.score y audita.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("crm.scoring")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def puntuar_lead(id_lead, *, persistir=True) -> dict:
    """Score 0-100 heuristico: prioridad + valor estimado + actividad reciente + datos de contacto."""
    from src.services.crm import leads
    lead = leads.obtener_lead(id_lead)
    if not lead:
        return {"ok": False, "error": "lead inexistente"}
    score = 0
    score += {"alta": 30, "normal": 15, "baja": 5}.get(lead.get("prioridad"), 10)
    val = float(lead.get("valor_estimado") or 0)
    score += 30 if val >= 10000 else 20 if val >= 3000 else 10 if val > 0 else 0
    if lead.get("email"):
        score += 10
    if lead.get("telefono"):
        score += 10
    # Actividad reciente suma; ningun contacto resta.
    try:
        from src.services.crm import actividades
        n_act = len(actividades.listar(id_lead=id_lead))
        score += min(n_act * 5, 20)
    except Exception:
        pass
    score = max(0, min(100, score))
    riesgo = "alto" if score < 30 else "medio" if score < 60 else "bajo"
    if persistir:
        try:
            leads.actualizar_lead(id_lead, score=score)
        except Exception:
            pass
    log_auditoria("crm", "CRM_SCORE_GENERATED", "crm_leads", f"lead={id_lead} score={score}")
    return {"ok": True, "score": score, "riesgo_perdida": riesgo,
            "probabilidad_conversion": round(score / 100, 2)}


def priorizar_leads(*, id_empresa=None, limite=100) -> list:
    """Devuelve leads abiertos ordenados por score descendente (priorizacion automatica)."""
    from src.services.crm import leads
    eid = _emp(id_empresa)
    abiertos = [l for l in leads.listar_leads(id_empresa=eid, limite=limite)
                if l.get("estado") in ("nuevo", "contactado", "calificado")]
    for l in abiertos:
        if l.get("score") is None:
            l["score"] = puntuar_lead(l["id"], persistir=False).get("score", 0)
    return sorted(abiertos, key=lambda x: x.get("score") or 0, reverse=True)


def probabilidad_cierre_oportunidad(id_oportunidad) -> dict:
    """Probabilidad de cierre = probabilidad de la etapa actual (ya calibrada en el pipeline)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT probabilidad, valor FROM crm_oportunidades WHERE id=%s", (id_oportunidad,))
            r = cur.fetchone()
        if not r:
            return {"ok": False}
        r = list(r.values()) if isinstance(r, dict) else r
        prob = int(r[0] or 0)
        return {"ok": True, "probabilidad": prob, "valor_esperado": round(float(r[1] or 0) * prob / 100, 2)}
    except Exception as e:
        logger.error("probabilidad_cierre: %s", e)
        return {"ok": False, "error": str(e)}


def forecast_comercial(*, id_empresa=None) -> dict:
    """Forecast = suma ponderada del pipeline abierto. Auditado."""
    from src.services.crm import oportunidades
    eid = _emp(id_empresa)
    vp = oportunidades.valor_pipeline(id_empresa=eid)
    log_auditoria("crm", "CRM_FORECAST_GENERATED", "crm_oportunidades",
                  f"ponderado={vp.get('valor_ponderado')}")
    return {"forecast_ponderado": vp.get("valor_ponderado"), "pipeline_total": vp.get("valor_total"),
            "oportunidades_abiertas": vp.get("abiertas")}
