"""
B7-I — Dashboard de resiliencia. Agrega estado online/offline, colas, eventos pendientes,
reintentos, conflictos, circuit breakers abiertos, RPO/RTO, ultima sincronizacion, servicios
degradados y salud general. Publica metricas en observabilidad (Prometheus /metrics). Integra DR/BI.
"""

import logging
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("resiliencia.dashboard")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def panel(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    from src.services.resiliencia import circuit_breaker, edge_node, outbox, rpo_rto
    out = {}
    try:
        from src.services.observabilidad import health
        h = health.health()
        out["salud"] = h.get("status")
        out["subsistemas"] = h.get("subsistemas", {})
        out["servicios_degradados"] = [k for k, v in h.get("subsistemas", {}).items() if v is False]
    except Exception:
        out["salud"] = "desconocida"; out["servicios_degradados"] = []
    m = outbox.metricas(id_empresa=eid)
    out["colas"] = m.get("outbox", {})
    out["sync_pendientes"] = m.get("pendientes", 0)
    out["conflictos"] = m.get("conflictos_abiertos", 0)
    out["circuit_breakers"] = circuit_breaker.estado(id_empresa=eid)
    out["breakers_abiertos"] = [b["servicio"] for b in circuit_breaker.abiertos(id_empresa=eid)]
    out["rpo_rto"] = rpo_rto.rpo_rto_empresa(id_empresa=eid)
    nodos = edge_node.listar(id_empresa=eid)
    out["edge_nodes"] = nodos
    out["tiendas_offline"] = sum(1 for n in nodos if n.get("modo") in ("offline", "degradado"))
    out["ultima_sincronizacion"] = max((str(n.get("ultima_sincronizacion")) for n in nodos
                                        if n.get("ultima_sincronizacion")), default=None)
    return out


def publicar_metricas(*, id_empresa=None) -> dict:
    """Publica las metricas de resiliencia en observabilidad (Prometheus /metrics)."""
    eid = _emp(id_empresa)
    p = panel(id_empresa=eid)
    try:
        from src.services.observabilidad import metricas
        metricas.set_gauge("sync_pending_total", p.get("sync_pendientes", 0))
        metricas.set_gauge("sync_failed_total", p.get("colas", {}).get("fallido", 0))
        metricas.set_gauge("circuit_breakers_open", len(p.get("breakers_abiertos", [])))
        metricas.set_gauge("store_offline_count", p.get("tiendas_offline", 0))
        rr = p.get("rpo_rto", {})
        if rr.get("rpo_backup") is not None:
            metricas.set_gauge("rpo_current", rr["rpo_backup"])
        if rr.get("rto_backup") is not None:
            metricas.set_gauge("rto_current", rr["rto_backup"])
        metricas.set_gauge("offline_events_total", rr.get("eventos_pendientes", 0))
    except Exception as e:
        logger.debug("publicar_metricas: %s", e)
    return p


def _job_metricas(id_empresa):
    p = publicar_metricas(id_empresa=id_empresa)
    return f"sync_pendientes={p.get('sync_pendientes')} breakers={len(p.get('breakers_abiertos', []))}"


def registrar_jobs_dashboard(id_empresa=None):
    from src.services import scheduler
    scheduler.registrar("resiliencia_metricas", _job_metricas)
    scheduler.registrar_job("resiliencia_metricas", intervalo_horas=1,
                            descripcion="Publicar metricas de resiliencia", id_empresa=id_empresa)
