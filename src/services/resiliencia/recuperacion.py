"""
Resiliencia · Orquestador de recuperación / Alta Disponibilidad (Etapa F · Fase F3).

COMPONE las primitivas de recuperación YA EXISTENTES en una operación única de autoheal/HA, sin crear
mecanismos nuevos ni motores paralelos (Reglas 6/7):

  · Outbox + sync → `resiliencia.resilience_watchdog.ejecutar` (reencola agotados, reanuda sync).
  · Scheduler → `scheduler_enterprise.core.procesar_pendientes` (ejecuta los schedules vencidos).
  · Inbox → idempotente por `idempotency_key` (el reproceso NO duplica); se reporta el backlog.
  · Event Bus → RECUPERACIÓN SEGURA por `replay` (reconstrucción, solo lectura). NO se reentregan
    eventos: `estado='pendiente'` es el estado por defecto (no un fallo de entrega), así que reentregar
    causaría doble procesamiento. Se reporta el backlog reconstruible.
  · Nodos / Failover → `platform.cloud.nodes/heartbeat` (latidos obsoletos) + `edge_node` (offline).

Solo lectura salvo las acciones idempotentes de recuperación existentes. Degradable, multiempresa,
aditivo y reversible.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("resiliencia.recuperacion")

FASE = "F3"


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


def recuperar_outbox(id_empresa=None, *, aplicar=True) -> dict:
    """Recuperación de Outbox + sync reutilizando el watchdog de resiliencia (reencola reintentos
    agotados y reanuda la sincronización). Idempotente."""
    try:
        from src.services.resiliencia import resilience_watchdog
        r = resilience_watchdog.ejecutar(id_empresa=id_empresa, aplicar=aplicar)
        return {"acciones": r.get("acciones", []),
                "outbox_pendiente": (r.get("diagnostico") or {}).get("outbox_pendiente", 0),
                "outbox_agotado": (r.get("diagnostico") or {}).get("outbox_agotado", 0)}
    except Exception as e:
        logger.debug("recuperar_outbox: %s", e)
        return {"acciones": []}


def recuperar_scheduler(id_empresa=None, *, aplicar=True) -> dict:
    """Recuperación del Scheduler: ejecuta los schedules vencidos (`procesar_pendientes`, idempotente por
    schedule) y reporta vencidos/fallidos. No crea un scheduler nuevo."""
    emp = _emp(id_empresa)
    out = {"ejecutados": 0}
    out["vencidos"] = _scalar(
        "SELECT COUNT(*) FROM scheduler_schedules WHERE id_empresa=%s AND estado='activo' AND "
        "proxima_ejecucion IS NOT NULL AND proxima_ejecucion<=NOW()", (emp,))
    out["fallidos"] = _scalar(
        "SELECT COUNT(*) FROM scheduler_ejecuciones WHERE id_empresa=%s AND estado='fallido'", (emp,))
    if aplicar:
        try:
            from src.services.scheduler_enterprise import core as sch
            out["ejecutados"] = int(sch.procesar_pendientes(emp) or 0)
        except Exception as e:
            logger.debug("recuperar_scheduler procesar: %s", e)
    return out


def recuperar_inbox(id_empresa=None) -> dict:
    """Estado del Inbox: idempotente por `idempotency_key` (el reproceso no duplica). Reporta backlog."""
    emp = _emp(id_empresa)
    return {"backlog": _scalar("SELECT COUNT(*) FROM sync_inbox WHERE id_empresa=%s", (emp,)),
            "idempotente": True}


def recuperar_eventbus(id_empresa=None) -> dict:
    """Recuperación del Event Bus por REPLAY (reconstrucción, solo lectura). NO reentrega eventos para
    evitar doble procesamiento. Reporta el nº de eventos reconstruibles."""
    emp = _emp(id_empresa)
    reconstruibles = 0
    try:
        from src.services import eventbus
        reconstruibles = len(eventbus.replay(id_empresa=emp) or [])
    except Exception as e:
        logger.debug("recuperar_eventbus: %s", e)
    return {"reconstruibles": reconstruibles, "metodo": "replay", "reentrega": False}


def estado_ha(id_empresa=None) -> dict:
    """Estado de Alta Disponibilidad: nodos registrados/disponibles, latidos obsoletos (stale),
    candidatos a failover y nodos edge offline. Reutiliza platform.cloud + edge_node."""
    ha = {}
    try:
        from src.platform.cloud import heartbeat, nodes
        ha["nodos"] = len(nodes.listar())
        disponibles = nodes.disponibles()
        ha["disponibles"] = len(disponibles)
        ha["stale"] = heartbeat.stale()
        ha["failover_candidatos"] = len(disponibles)     # hay a quién promover si cae el primario
    except Exception as e:
        logger.debug("estado_ha nodos: %s", e)
    try:
        from src.services.resiliencia import edge_node
        edges = edge_node.listar(id_empresa=_emp(id_empresa)) or []
        ha["edge_total"] = len(edges)
        ha["edge_offline"] = sum(1 for e in edges if str(e.get("modo", "")).lower() == "offline")
    except Exception as e:
        logger.debug("estado_ha edge: %s", e)
    return ha


def recuperar_todo(id_empresa=None, *, aplicar=True) -> dict:
    """Autoheal/HA unificado: compone Outbox, Scheduler, Inbox, Event Bus (replay) y estado HA. Las
    recuperaciones activas (outbox/scheduler) son idempotentes; Event Bus e Inbox solo se reportan."""
    emp = _emp(id_empresa)
    return {"id_empresa": emp, "aplicar": aplicar,
            "outbox": recuperar_outbox(emp, aplicar=aplicar),
            "scheduler": recuperar_scheduler(emp, aplicar=aplicar),
            "inbox": recuperar_inbox(emp),
            "eventbus": recuperar_eventbus(emp),
            "ha": estado_ha(emp)}


def registrar_job(id_empresa=None) -> bool:
    """Registra la recuperación periódica en el Scheduler (capacidad, degradable/opt-in)."""
    try:
        from src.services.scheduler_enterprise import core as sch
        sch.registrar_job("resiliencia_recuperar_todo", lambda *_a, **_k: recuperar_todo())
        return True
    except Exception as e:
        logger.debug("registrar_job recuperacion: %s", e)
        return False


def descriptor() -> dict:
    return {"servicio": "resiliencia.recuperacion", "etapa": "F", "fase": FASE,
            "estado": "implementado", "motor_nuevo": False, "reentrega_eventos": False,
            "reutiliza": ["resilience_watchdog (outbox/sync)", "scheduler_enterprise.procesar_pendientes",
                          "eventbus.replay", "sync_inbox (idempotente)", "platform.cloud (nodos/failover)",
                          "edge_node"],
            "operaciones": ["recuperar_outbox", "recuperar_scheduler", "recuperar_inbox",
                            "recuperar_eventbus", "estado_ha", "recuperar_todo"]}


__all__ = ["FASE", "recuperar_outbox", "recuperar_scheduler", "recuperar_inbox", "recuperar_eventbus",
           "estado_ha", "recuperar_todo", "registrar_job", "descriptor"]
