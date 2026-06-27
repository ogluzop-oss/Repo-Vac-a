"""
FASE F — IA financiera. Amplia el Prophet existente (prevision_financiera/bi forecasting) y añade
deteccion de anomalias financieras, riesgo de tesoreria, prediccion de impagos y riesgo de credito.
Todo EXPLICABLE y auditable (sin cajas negras): heuristicas transparentes + Prophet degradable.
"""

import logging
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("finanzas.ia")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def prediccion_liquidez(*, id_empresa=None) -> dict:
    """Reutiliza la proyeccion de liquidez existente (Prophet/media) sin duplicarla."""
    eid = _emp(id_empresa)
    try:
        from src.services.tesoreria import prevision_financiera as PF
        return PF.proyeccion_liquidez(id_empresa=eid)
    except Exception as e:
        logger.error("prediccion_liquidez: %s", e)
        return {}


def riesgo_tesoreria(*, id_empresa=None) -> dict:
    """Riesgo de tesoreria: proyeccion negativa de liquidez -> nivel + horizonte. Explicable."""
    eid = _emp(id_empresa)
    proy = prediccion_liquidez(id_empresa=eid)
    proyecciones = proy.get("proyecciones", []) if isinstance(proy, dict) else []
    negativos = [p for p in proyecciones if float(p.get("liquidez_estimada", 0)) < 0]
    if not negativos:
        return {"nivel": "bajo", "explicacion": "Sin proyeccion negativa de liquidez", "horizontes": []}
    primer = min(negativos, key=lambda p: p.get("horizonte_dias", 999))
    h = primer.get("horizonte_dias", 0)
    nivel = "critico" if h <= 30 else "alto" if h <= 90 else "medio"
    return {"nivel": nivel, "horizonte_dias": h,
            "explicacion": f"Liquidez estimada negativa a {h} dias",
            "horizontes": [p.get("horizonte_dias") for p in negativos]}


def deteccion_anomalias(*, id_empresa=None, factor=2.5) -> list:
    """Anomalias en movimientos de tesoreria: importes fuera de media ± factor*desv. Explicable."""
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, fecha, importe, concepto FROM movimientos_tesoreria WHERE id_empresa=%s "
                        "ORDER BY fecha DESC LIMIT 1000", (eid,))
            movs = [(r if isinstance(r, dict) else {"id": r[0], "fecha": r[1], "importe": r[2], "concepto": r[3]})
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("deteccion_anomalias: %s", e)
        return []
    vals = [abs(float(m["importe"] or 0)) for m in movs]
    if len(vals) < 5:
        return []
    media = sum(vals) / len(vals)
    desv = (sum((x - media) ** 2 for x in vals) / len(vals)) ** 0.5
    if desv <= 0:
        return []
    umbral = media + factor * desv
    return [{"id": m["id"], "fecha": str(m["fecha"]), "importe": float(m["importe"]),
             "concepto": m.get("concepto"), "umbral": round(umbral, 2),
             "explicacion": f"Importe {abs(float(m['importe'])):.2f} supera el umbral {umbral:.2f}"}
            for m in movs if abs(float(m["importe"] or 0)) > umbral]


def prediccion_impagos(*, id_empresa=None) -> list:
    """Clientes con riesgo de impago: vencimientos COBRO vencidos + score de credito bajo. Explicable."""
    eid = _emp(id_empresa)
    riesgos = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, nombre FROM clientes WHERE id_empresa=%s LIMIT 1000", (eid,))
            clientes = [(r if isinstance(r, dict) else {"id": r[0], "nombre": r[1]}) for r in cur.fetchall()]
    except Exception as e:
        logger.error("prediccion_impagos: %s", e)
        return []
    from src.services.finanzas import credito
    for c in clientes:
        sc = credito.calcular_score(c["id"], persistir=False, id_empresa=eid)
        if sc["nivel_riesgo"] in ("alto", "critico"):
            riesgos.append({"id_cliente": c["id"], "nombre": c.get("nombre"), "score": sc["score"],
                            "nivel": sc["nivel_riesgo"], "explicacion": sc["explicacion"]})
    return sorted(riesgos, key=lambda x: x["score"])


def recomendaciones(*, id_empresa=None) -> list:
    """Acciones sugeridas priorizadas, derivadas de los analisis anteriores. Auditado."""
    eid = _emp(id_empresa)
    recs = []
    rt = riesgo_tesoreria(id_empresa=eid)
    if rt["nivel"] in ("alto", "critico"):
        recs.append({"prioridad": 1, "tipo": "tesoreria",
                     "accion": "Revisar lineas de credito / aplazar pagos", "motivo": rt["explicacion"]})
    impagos = prediccion_impagos(id_empresa=eid)
    if impagos:
        recs.append({"prioridad": 2, "tipo": "credito",
                     "accion": f"Gestionar cobro de {len(impagos)} clientes de alto riesgo",
                     "motivo": "Clientes con score de credito bajo"})
    anomalias = deteccion_anomalias(id_empresa=eid)
    if anomalias:
        recs.append({"prioridad": 3, "tipo": "anomalia",
                     "accion": f"Revisar {len(anomalias)} movimientos atipicos",
                     "motivo": "Importes fuera del patron habitual"})
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("finanzas", "FIN_IA_RECOMENDACIONES", "ia", f"n={len(recs)}")
    except Exception:
        pass
    return recs
