"""
GMAO-F/G — KPIs de mantenimiento (BI) + IA predictiva (riesgo de averia) sin dependencias externas.
KPIs: MTTR, MTBF, disponibilidad, cumplimiento preventivo, coste, averias recurrentes.
IA: riesgo de averia por activo a partir del historico de OT correctivas (heuristico/Prophet degradable).
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("gmao.analitica")


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
            # MTTR: media de horas de reparacion (fin - inicio) en OT correctivas finalizadas.
            cur.execute("SELECT AVG(TIMESTAMPDIFF(HOUR, fecha_inicio, fecha_fin)) FROM ordenes_trabajo "
                        "WHERE id_empresa=%s AND tipo='correctiva' AND estado='finalizada' "
                        "AND fecha_inicio IS NOT NULL AND fecha_fin IS NOT NULL", (eid,))
            out["mttr_horas"] = round(float(_val(cur)), 2)
            # MTBF: tiempo medio entre averias correctivas por activo.
            cur.execute("SELECT COUNT(*) FROM ordenes_trabajo WHERE id_empresa=%s AND tipo='correctiva'", (eid,))
            averias = int(_val(cur))
            out["averias_correctivas"] = averias
            cur.execute("SELECT COUNT(DISTINCT id_activo) FROM ordenes_trabajo WHERE id_empresa=%s "
                        "AND tipo='correctiva' AND id_activo IS NOT NULL", (eid,))
            activos_con_averia = int(_val(cur))
            # MTBF aproximado: horas del periodo / averias (si hay datos).
            out["mtbf_horas"] = round((30 * 24 * max(activos_con_averia, 1)) / averias, 2) if averias else None
            # Disponibilidad = 1 - (horas en mantenimiento / horas totales activos) aprox.
            cur.execute("SELECT COUNT(*) FROM activos WHERE id_empresa=%s AND estado='operativo'", (eid,))
            operativos = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM activos WHERE id_empresa=%s", (eid,))
            total_activos = int(_val(cur))
            out["disponibilidad_pct"] = round(operativos * 100 / total_activos, 1) if total_activos else 100.0
            # Cumplimiento preventivo = preventivas finalizadas a tiempo / preventivas.
            cur.execute("SELECT COUNT(*) FROM ordenes_trabajo WHERE id_empresa=%s AND tipo='preventiva'", (eid,))
            prev = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM ordenes_trabajo WHERE id_empresa=%s AND tipo='preventiva' "
                        "AND estado='finalizada'", (eid,))
            out["cumplimiento_preventivo_pct"] = round(int(_val(cur)) * 100 / prev, 1) if prev else 0
            cur.execute("SELECT COALESCE(SUM(coste_real),0) FROM costes_ot WHERE id_empresa=%s", (eid,))
            out["coste_mantenimiento"] = round(float(_val(cur)), 2)
    except Exception as e:
        logger.error("kpis: %s", e)
    return out


def averias_recurrentes(*, id_empresa=None, umbral=3) -> list:
    """Activos con >= umbral OT correctivas (candidatos a mantenimiento predictivo)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT o.id_activo, a.codigo, a.nombre, COUNT(*) n FROM ordenes_trabajo o "
                        "LEFT JOIN activos a ON a.id=o.id_activo WHERE o.id_empresa=%s AND o.tipo='correctiva' "
                        "AND o.id_activo IS NOT NULL GROUP BY o.id_activo HAVING n >= %s ORDER BY n DESC",
                        (eid, int(umbral)))
            return [(r if isinstance(r, dict) else {"id_activo": r[0], "codigo": r[1], "nombre": r[2], "averias": r[3]})
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("averias_recurrentes: %s", e)
        return []


def registrar_en_bi(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    k = kpis(id_empresa=eid)
    try:
        from src.services.bi import kpis as bi_kpis
        if hasattr(bi_kpis, "guardar_valor"):
            for nombre, valor in k.items():
                if isinstance(valor, (int, float)):
                    bi_kpis.guardar_valor(f"gmao_{nombre}", valor, id_empresa=eid)
    except Exception as e:
        logger.debug("registrar_en_bi: %s", e)
    return k


def riesgo_averia(id_activo, *, id_empresa=None) -> dict:
    """IA predictiva: riesgo de averia segun frecuencia historica de correctivas + criticidad."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), MAX(fecha_creacion) FROM ordenes_trabajo WHERE id_empresa=%s "
                        "AND id_activo=%s AND tipo='correctiva'", (eid, id_activo))
            r = cur.fetchone(); r = list(r.values()) if isinstance(r, dict) else r
            n_averias = int(r[0] or 0)
            cur.execute("SELECT criticidad FROM activos WHERE id=%s", (id_activo,))
            rc = cur.fetchone()
            criticidad = (rc[0] if not isinstance(rc, dict) else list(rc.values())[0]) if rc else "media"
    except Exception as e:
        logger.error("riesgo_averia: %s", e)
        return {"ok": False, "error": str(e)}
    score = min(100, n_averias * 15 + {"alta": 30, "media": 15, "baja": 5}.get(criticidad, 10))
    nivel = "alto" if score >= 60 else "medio" if score >= 30 else "bajo"
    return {"ok": True, "id_activo": id_activo, "averias_historicas": n_averias,
            "riesgo": nivel, "score": score}


def activos_criticos(*, id_empresa=None) -> list:
    """Activos con mayor riesgo de averia (priorizacion de mantenimiento predictivo)."""
    eid = _emp(id_empresa)
    from src.services.gmao import activos as _act
    out = []
    for a in _act.listar(id_empresa=eid):
        r = riesgo_averia(a["id"], id_empresa=eid)
        if r.get("ok") and r["score"] >= 30:
            out.append({"id_activo": a["id"], "codigo": a.get("codigo"), "riesgo": r["riesgo"], "score": r["score"]})
    return sorted(out, key=lambda x: x["score"], reverse=True)
