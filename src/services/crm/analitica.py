"""
CRM-G — Analitica CRM. KPIs comerciales calculados sobre los datos reales del CRM.
Reutiliza oportunidades/leads/crm_saas (no duplica BI: expone metricas listas para BI/dashboard).
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("crm.analitica")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _scalar(cur):
    r = cur.fetchone()
    if not r:
        return 0
    return (list(r.values())[0] if isinstance(r, dict) else r[0]) or 0


def kpis(*, id_empresa=None) -> dict:
    """KPIs: leads nuevos/calificados, conversion, tasa de cierre, tiempo medio, valor pipeline,
    forecast, clientes SaaS nuevos, churn comercial."""
    eid = _emp(id_empresa)
    out = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM crm_leads WHERE id_empresa=%s AND estado='nuevo'", (eid,))
            out["leads_nuevos"] = int(_scalar(cur))
            cur.execute("SELECT COUNT(*) FROM crm_leads WHERE id_empresa=%s AND estado='calificado'", (eid,))
            out["leads_calificados"] = int(_scalar(cur))
            cur.execute("SELECT COUNT(*) FROM crm_leads WHERE id_empresa=%s", (eid,))
            total_leads = int(_scalar(cur))
            cur.execute("SELECT COUNT(*) FROM crm_leads WHERE id_empresa=%s AND estado='convertido'", (eid,))
            convertidos = int(_scalar(cur))
            out["conversion_pct"] = round(convertidos * 100 / total_leads, 1) if total_leads else 0
            # Tasa de cierre = ganadas / (ganadas+perdidas).
            cur.execute("SELECT COUNT(*) FROM crm_oportunidades WHERE id_empresa=%s AND estado='ganada'", (eid,))
            ganadas = int(_scalar(cur))
            cur.execute("SELECT COUNT(*) FROM crm_oportunidades WHERE id_empresa=%s AND estado='perdida'", (eid,))
            perdidas = int(_scalar(cur))
            out["tasa_cierre_pct"] = round(ganadas * 100 / (ganadas + perdidas), 1) if (ganadas + perdidas) else 0
            cur.execute("SELECT AVG(DATEDIFF(fecha_cierre, fecha_creacion)) FROM crm_oportunidades "
                        "WHERE id_empresa=%s AND fecha_cierre IS NOT NULL", (eid,))
            out["tiempo_medio_cierre_dias"] = round(float(_scalar(cur)), 1)
            cur.execute("SELECT COUNT(*) FROM crm_saas_funnel WHERE fase='cliente'")
            out["clientes_saas_nuevos"] = int(_scalar(cur))
            cur.execute("SELECT COUNT(*) FROM crm_saas_funnel WHERE fase='perdido'")
            out["churn_comercial"] = int(_scalar(cur))
    except Exception as e:
        logger.error("kpis: %s", e)
    # Valor pipeline + forecast reutilizando oportunidades.
    try:
        from src.services.crm import oportunidades
        vp = oportunidades.valor_pipeline(id_empresa=eid)
        out["valor_pipeline"] = vp.get("valor_total")
        out["forecast"] = vp.get("valor_ponderado")
    except Exception:
        pass
    return out


def registrar_en_bi(*, id_empresa=None) -> dict:
    """Best-effort: publica los KPIs CRM en el data warehouse BI si esta disponible."""
    eid = _emp(id_empresa)
    k = kpis(id_empresa=eid)
    try:
        from src.services.bi import kpis as bi_kpis
        if hasattr(bi_kpis, "guardar_valor"):
            for nombre, valor in k.items():
                if isinstance(valor, (int, float)):
                    bi_kpis.guardar_valor(f"crm_{nombre}", valor, id_empresa=eid)
    except Exception as e:
        logger.debug("registrar_en_bi: %s", e)
    return k
