"""
CAL-F/H — KPIs de calidad (BI) + IA (deteccion de anomalias / tendencias de rechazo).
Datos exclusivamente internos. IA degradable (heuristica si no hay datos suficientes).
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("calidad.analitica")


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
            cur.execute("SELECT COALESCE(SUM(cantidad_inspeccionada),0), COALESCE(SUM(cantidad_rechazada),0) "
                        "FROM inspecciones WHERE id_empresa=%s", (eid,))
            r = cur.fetchone(); r = list(r.values()) if isinstance(r, dict) else r
            insp, rech = float(r[0] or 0), float(r[1] or 0)
            out["unidades_inspeccionadas"] = insp
            out["unidades_rechazadas"] = rech
            out["tasa_rechazo_pct"] = round(rech * 100 / insp, 2) if insp else 0
            cur.execute("SELECT COUNT(*) FROM inspecciones WHERE id_empresa=%s AND resultado='rechazada'", (eid,))
            out["inspecciones_rechazadas"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM no_conformidades WHERE id_empresa=%s", (eid,))
            out["nc_total"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM no_conformidades WHERE id_empresa=%s AND estado NOT IN "
                        "('cerrada','rechazada')", (eid,))
            out["nc_abiertas"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM acciones_correctivas WHERE id_empresa=%s AND estado!='cerrada'", (eid,))
            out["capa_abiertas"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM acciones_correctivas WHERE id_empresa=%s AND estado='cerrada'", (eid,))
            out["capa_cerradas"] = int(_val(cur))
            # Coste de calidad aproximado = mermas valoradas (reutiliza mermas)
            cur.execute("SELECT COALESCE(SUM(cantidad),0) FROM mermas WHERE id_empresa=%s", (eid,))
            out["unidades_merma"] = float(_val(cur))
    except Exception as e:
        logger.error("kpis calidad: %s", e)
    return out


def registrar_en_bi(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    k = kpis(id_empresa=eid)
    try:
        from src.services.bi import kpis as bi_kpis
        if hasattr(bi_kpis, "guardar_valor"):
            for nombre, valor in k.items():
                if isinstance(valor, (int, float)):
                    bi_kpis.guardar_valor(f"calidad_{nombre}", valor, id_empresa=eid)
    except Exception as e:
        logger.debug("registrar_en_bi: %s", e)
    return k


def deteccion_anomalias(*, id_empresa=None, factor=2.0) -> list:
    """Detecta articulos con tasa de rechazo anomala (> media + factor*desv) sobre el historico."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT articulo, COALESCE(SUM(cantidad_inspeccionada),0) ins, "
                        "COALESCE(SUM(cantidad_rechazada),0) rec FROM inspecciones WHERE id_empresa=%s "
                        "AND articulo IS NOT NULL GROUP BY articulo HAVING ins > 0", (eid,))
            filas = [(r if isinstance(r, dict) else {"articulo": r[0], "ins": r[1], "rec": r[2]})
                     for r in cur.fetchall()]
    except Exception as e:
        logger.error("deteccion_anomalias: %s", e)
        return []
    tasas = [(f["articulo"], float(f["rec"]) / float(f["ins"])) for f in filas if float(f["ins"]) > 0]
    if len(tasas) < 3:
        return []
    vals = [t for _, t in tasas]
    media = sum(vals) / len(vals)
    desv = (sum((v - media) ** 2 for v in vals) / len(vals)) ** 0.5
    umbral = media + factor * desv
    return [{"articulo": a, "tasa_rechazo": round(t, 3), "umbral": round(umbral, 3)}
            for a, t in tasas if t > umbral and desv > 0]


def tendencia_rechazo(articulo, *, id_empresa=None) -> dict:
    """Tendencia de la tasa de rechazo del articulo por mes (analisis de incidencias)."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DATE_FORMAT(fecha,'%%Y-%%m') m, COALESCE(SUM(cantidad_inspeccionada),0) ins, "
                        "COALESCE(SUM(cantidad_rechazada),0) rec FROM inspecciones WHERE id_empresa=%s "
                        "AND articulo=%s GROUP BY m ORDER BY m", (eid, articulo))
            serie = [{"mes": (r[0] if not isinstance(r, dict) else list(r.values())[0]),
                      "tasa": round(float((r[2] if not isinstance(r, dict) else list(r.values())[2]) or 0) /
                                    float((r[1] if not isinstance(r, dict) else list(r.values())[1]) or 1), 3)}
                     for r in cur.fetchall()]
    except Exception as e:
        logger.error("tendencia_rechazo: %s", e)
        serie = []
    direccion = "estable"
    if len(serie) >= 2:
        direccion = "subiendo" if serie[-1]["tasa"] > serie[0]["tasa"] else \
                    "bajando" if serie[-1]["tasa"] < serie[0]["tasa"] else "estable"
    return {"articulo": articulo, "serie": serie, "tendencia": direccion}
