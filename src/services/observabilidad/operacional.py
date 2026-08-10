"""
Observabilidad · Métricas operacionales (Etapa F · Fase F1).

Recolector PULL que ALIMENTA el motor de métricas ÚNICO (`observabilidad.metricas`, Prometheus) con
gauges operacionales de **Scheduler / Event Bus / Marketplace / SDK**, leyendo el estado desde los
servicios existentes. NO crea un motor nuevo ni duplica observabilidad: reutiliza `metricas.set_gauge`
y las API públicas de cada subsistema. Degradable (cada fuente en try/except; si una capacidad no está,
su gauge se omite). Solo lectura. Multiempresa. Aditivo y retrocompatible.

Se invoca en el scrape de `/api/v1/metrics` (junto a `metricas.actualizar_negocio`) para que las métricas
operacionales queden expuestas en Prometheus sin instrumentar cada motor por separado.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("observabilidad.operacional")

FASE = "F1"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _scalar(sql, params=()):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
    except Exception:
        return 0


def _scheduler(emp) -> dict:
    out = {}
    try:
        from src.services.scheduler_enterprise import core as sch
        out["activos"] = len(sch.listar_schedules(emp, estado="activo") or [])
        out["pausados"] = len(sch.listar_schedules(emp, estado="pausado") or [])
    except Exception as e:
        logger.debug("operacional scheduler: %s", e)
    out["ejecuciones_fallidas"] = _scalar(
        "SELECT COUNT(*) FROM scheduler_ejecuciones WHERE id_empresa=%s AND estado='fallido'", (emp,))
    return out


def _eventbus(emp) -> dict:
    out = {}
    try:
        from src.services import eventbus
        subs = eventbus.suscripciones() or {}
        out["suscripciones"] = sum(len(v or []) for v in subs.values()) if isinstance(subs, dict) else 0
    except Exception as e:
        logger.debug("operacional eventbus subs: %s", e)
    out["eventos_total"] = _scalar("SELECT COUNT(*) FROM eventos WHERE id_empresa=%s", (emp,))
    out["eventos_pendientes"] = _scalar(
        "SELECT COUNT(*) FROM eventos WHERE id_empresa=%s AND estado='pendiente'", (emp,))
    return out


def _marketplace(emp) -> dict:
    out = {}
    try:
        from src.services import marketplace
    except Exception as e:
        logger.debug("operacional marketplace import: %s", e)
        return out
    try:
        out["catalogo"] = len(marketplace.catalogo(emp) or [])
    except Exception as e:
        logger.debug("operacional marketplace catalogo: %s", e)
    try:
        out["actualizaciones"] = len(marketplace.actualizaciones_disponibles(emp) or [])
    except Exception as e:
        logger.debug("operacional marketplace actualizaciones: %s", e)
    return out


def _sdk(emp) -> dict:
    out = {}
    try:
        from src import sdk
        out["plugins_instalados"] = len(sdk.listar_instalados(emp) or [])
    except Exception as e:
        logger.debug("operacional sdk: %s", e)
    return out


def snapshot(id_empresa=None) -> dict:
    """Estado operacional (dict) de Scheduler/Event Bus/Marketplace/SDK. Solo lectura, degradable."""
    emp = _emp(id_empresa)
    return {"scheduler": _scheduler(emp), "eventbus": _eventbus(emp),
            "marketplace": _marketplace(emp), "sdk": _sdk(emp)}


# (dominio, clave) → nombre del gauge Prometheus.
_GAUGES = {
    ("scheduler", "activos"): "sm_scheduler_schedules_activos",
    ("scheduler", "pausados"): "sm_scheduler_schedules_pausados",
    ("scheduler", "ejecuciones_fallidas"): "sm_scheduler_ejecuciones_fallidas",
    ("eventbus", "suscripciones"): "sm_eventbus_suscripciones",
    ("eventbus", "eventos_total"): "sm_eventbus_eventos_total",
    ("eventbus", "eventos_pendientes"): "sm_eventbus_eventos_pendientes",
    ("marketplace", "catalogo"): "sm_marketplace_catalogo_total",
    ("marketplace", "actualizaciones"): "sm_marketplace_actualizaciones_disponibles",
    ("sdk", "plugins_instalados"): "sm_sdk_plugins_instalados",
}


def recolectar(id_empresa=None) -> dict:
    """Lee el estado operacional y lo publica como gauges en el motor de métricas ÚNICO (Prometheus).
    Devuelve el snapshot. Degradable: si `metricas` no está, solo devuelve el snapshot."""
    snap = snapshot(id_empresa)
    try:
        from src.services.observabilidad import metricas
        for (dom, clave), nombre in _GAUGES.items():
            val = (snap.get(dom) or {}).get(clave)
            if val is not None:
                metricas.set_gauge(nombre, val)
    except Exception as e:
        logger.debug("operacional recolectar set_gauge: %s", e)
    return snap


def descriptor() -> dict:
    return {"servicio": "observabilidad.operacional", "etapa": "F", "fase": FASE,
            "estado": "implementado", "solo_lectura": True, "motor_nuevo": False,
            "reutiliza": ["observabilidad.metricas (Prometheus)", "scheduler_enterprise", "eventbus",
                          "marketplace", "sdk"],
            "gauges": sorted(_GAUGES.values())}


__all__ = ["FASE", "snapshot", "recolectar", "descriptor"]
