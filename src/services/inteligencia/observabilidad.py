"""
Etapa C · Fase C5 — Observabilidad avanzada de la inteligencia (Área 9).

Registra y RECONSTRUYE toda la actividad del Centro de Decisiones: propuestas, recomendaciones,
predicciones, aceptaciones, rechazos y feedback. No crea tablas ni motores nuevos: agrega sobre el
ledger `decisiones_ia` (C1) y reutiliza el Event Bus para el Decision/Audit Replay. Solo lectura,
RBAC (`inteligencia.ver`), multiempresa, degradable.
"""

from __future__ import annotations

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("inteligencia.observabilidad")

FASE = "C5"


def _emp(id_empresa=None):
    from src.services import inteligencia
    return inteligencia._emp(id_empresa)


def _puede(usuario, emp):
    from src.services import inteligencia
    return inteligencia._puede(usuario, "inteligencia.ver", emp)


def _grupo(cur, emp, campo, estado=None):
    sql = f"SELECT {campo}, COUNT(*) FROM decisiones_ia WHERE id_empresa=%s"
    params = [emp]
    if estado:
        sql += " AND estado=%s"
        params.append(estado)
    sql += f" GROUP BY {campo}"
    cur.execute(sql, tuple(params))
    out = {}
    for f in cur.fetchall():
        vals = list(f.values()) if isinstance(f, dict) else list(f)
        out[vals[0]] = int(vals[1])
    return out


def metricas(id_empresa=None, *, usuario=None):
    """Métricas de la inteligencia: recuentos por estado/tipo/origen/dominio, tasa de aceptación y
    volumen con feedback. Auditable, solo lectura."""
    emp = _emp(id_empresa)
    if not _puede(usuario, emp):
        return {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            por_estado = _grupo(cur, emp, "estado")
            por_tipo = _grupo(cur, emp, "tipo")
            por_origen = _grupo(cur, emp, "origen")
            por_dominio = _grupo(cur, emp, "dominio")
            cur.execute("SELECT COUNT(*) FROM decisiones_ia WHERE id_empresa=%s AND feedback IS NOT "
                        "NULL AND feedback<>''", (emp,))
            r = cur.fetchone()
            con_feedback = int(list(r.values())[0] if isinstance(r, dict) else r[0])
    except Exception as e:
        logger.error("metricas: %s", e)
        return {}
    acept = por_estado.get("aceptada", 0)
    rech = por_estado.get("rechazada", 0)
    total_resueltas = acept + rech
    tasa = round(acept / total_resueltas, 3) if total_resueltas else None
    return {"por_estado": por_estado, "por_tipo": por_tipo, "por_origen": por_origen,
            "por_dominio": por_dominio, "con_feedback": con_feedback,
            "tasa_aceptacion": tasa, "total": sum(por_estado.values())}


def replay(id_decision, *, id_empresa=None, usuario=None):
    """Reconstruye una decisión (Decision/Audit Replay): la decisión + sus eventos del Event Bus.
    Reconstructible y auditable."""
    from src.services import inteligencia
    emp = _emp(id_empresa)
    if not _puede(usuario, emp):
        return None
    dec = inteligencia.obtener(id_decision, id_empresa=emp, usuario=usuario)
    if not dec:
        return None
    eventos = []
    try:
        from src.platform import capabilities as cap
        bus = cap.eventbus()
        if bus is not None and hasattr(bus, "replay"):
            eventos = bus.replay(ref_entidad="decision_ia", ref_id=id_decision, id_empresa=emp) or []
    except Exception as e:
        logger.debug("replay eventos (%s): %s", id_decision, e)
    return {"decision": dec, "eventos": eventos, "correlation_id": dec.get("correlation_id"),
            "reconstruible": True}


def descriptor() -> dict:
    return {"servicio": "inteligencia.observabilidad", "etapa": "C", "fase": FASE,
            "estado": "implementado", "registra": ["propuestas", "recomendaciones", "predicciones",
            "aceptaciones", "rechazos", "feedback"], "reutiliza": ["decisiones_ia", "eventbus"],
            "solo_lectura": True, "auditable": True, "motor_nuevo": False}


__all__ = ["FASE", "metricas", "replay", "descriptor"]
