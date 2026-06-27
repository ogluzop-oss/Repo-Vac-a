"""
MRP-H/J — Analitica de fabricacion (KPIs) + IA (Prophet degradable).
KPIs: productividad, eficiencia, coste real, desviaciones, cumplimiento de planificacion.
IA: prevision de produccion/consumo de materiales reutilizando Prophet si esta disponible.
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("mrp.analitica")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _val(cur):
    r = cur.fetchone()
    if not r:
        return 0
    return (list(r.values())[0] if isinstance(r, dict) else r[0]) or 0


def kpis(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    out = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ordenes_fabricacion WHERE id_empresa=%s", (eid,))
            out["of_total"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM ordenes_fabricacion WHERE id_empresa=%s AND estado='finalizada'", (eid,))
            out["of_finalizadas"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM ordenes_fabricacion WHERE id_empresa=%s AND estado='en_curso'", (eid,))
            out["of_en_curso"] = int(_val(cur))
            # Productividad/eficiencia = producido / planificado en OF finalizadas
            cur.execute("SELECT COALESCE(SUM(cantidad_producida),0), COALESCE(SUM(cantidad),0) "
                        "FROM ordenes_fabricacion WHERE id_empresa=%s AND estado='finalizada'", (eid,))
            r = cur.fetchone(); r = list(r.values()) if isinstance(r, dict) else r
            prod, plan = float(r[0] or 0), float(r[1] or 0)
            out["eficiencia_pct"] = round(prod * 100 / plan, 1) if plan else 0
            out["unidades_producidas"] = prod
            # Coste real total y desviacion media
            cur.execute("SELECT COALESCE(SUM(coste_real),0), COALESCE(AVG(desviacion),0) FROM costes_of "
                        "WHERE id_empresa=%s", (eid,))
            r = cur.fetchone(); r = list(r.values()) if isinstance(r, dict) else r
            out["coste_real_total"] = round(float(r[0] or 0), 2)
            out["desviacion_media"] = round(float(r[1] or 0), 2)
            # Cumplimiento planificacion = finalizadas a tiempo / finalizadas
            cur.execute("SELECT COUNT(*) FROM ordenes_fabricacion WHERE id_empresa=%s AND estado='finalizada' "
                        "AND (fecha_prevista IS NULL OR DATE(fecha_fin) <= fecha_prevista)", (eid,))
            a_tiempo = int(_val(cur))
            out["cumplimiento_pct"] = round(a_tiempo * 100 / out["of_finalizadas"], 1) if out["of_finalizadas"] else 0
    except Exception as e:
        logger.error("kpis: %s", e)
    return out


def registrar_en_bi(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    k = kpis(id_empresa=eid)
    try:
        from src.services.bi import kpis as bi_kpis
        if hasattr(bi_kpis, "guardar_valor"):
            for nombre, valor in k.items():
                if isinstance(valor, (int, float)):
                    bi_kpis.guardar_valor(f"mrp_{nombre}", valor, id_empresa=eid)
    except Exception as e:
        logger.debug("registrar_en_bi: %s", e)
    return k


def prevision_produccion(articulo_final, *, horizonte=4, id_empresa=None) -> dict:
    """Prevision de produccion futura a partir del historico de of_produccion (Prophet si esta)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DATE(p.fecha) f, SUM(p.cantidad) c FROM of_produccion p "
                        "JOIN ordenes_fabricacion o ON o.id=p.id_of "
                        "WHERE o.id_empresa=%s AND o.articulo_final=%s GROUP BY DATE(p.fecha) ORDER BY f",
                        (eid, articulo_final))
            serie = [(str(r[0] if not isinstance(r, dict) else list(r.values())[0]),
                      float(r[1] if not isinstance(r, dict) else list(r.values())[1])) for r in cur.fetchall()]
    except Exception as e:
        logger.error("prevision_produccion: %s", e)
        serie = []
    if len(serie) < 3:
        media = round(sum(v for _, v in serie) / len(serie), 2) if serie else 0
        return {"metodo": "media", "prevision": [media] * horizonte, "puntos_historicos": len(serie)}
    # Prophet si disponible; si no, media movil.
    try:
        from prophet import Prophet  # noqa: F401
        import pandas as pd
        df = pd.DataFrame(serie, columns=["ds", "y"])
        df["ds"] = pd.to_datetime(df["ds"])
        m = Prophet(weekly_seasonality=False, daily_seasonality=False); m.fit(df)
        fut = m.make_future_dataframe(periods=horizonte)
        fc = m.predict(fut).tail(horizonte)["yhat"].tolist()
        return {"metodo": "prophet", "prevision": [round(max(0, v), 2) for v in fc], "puntos_historicos": len(serie)}
    except Exception:
        vals = [v for _, v in serie]
        media = round(sum(vals[-3:]) / 3, 2)
        return {"metodo": "media_movil", "prevision": [media] * horizonte, "puntos_historicos": len(serie)}


def simulacion_capacidad(id_centro, unidades, *, id_empresa=None) -> dict:
    """Estima los dias necesarios para producir `unidades` en un centro segun su capacidad."""
    from src.services.mrp import centros
    cap = centros.capacidad_diaria(id_centro)
    if cap <= 0:
        return {"ok": False, "error": "centro sin capacidad definida"}
    import math
    return {"ok": True, "capacidad_dia": cap, "dias_necesarios": math.ceil(unidades / cap)}
