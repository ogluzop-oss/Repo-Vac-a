"""
Cloud Observability · Métricas (Fase VI · Bloque 12). Dashboards de métricas para despliegues
distribuidos: nodos, regiones, clústeres, gateways, APIs, Event Bus, Scheduler, Workflow y CCP.
Reutiliza las métricas Enterprise (`observabilidad.metricas`) y el Node Registry cloud. Descriptores
+ agregación (sin motor de métricas nuevo).
"""

from __future__ import annotations

DASHBOARDS = ("nodos", "regiones", "clusteres", "gateways", "apis", "eventbus", "scheduler",
              "workflow", "ccp")


def metricas_nodos() -> dict:
    from src.platform import cloud
    nodos = cloud.nodes.listar()
    return {"total": len(nodos), "disponibles": len(cloud.nodes.disponibles()),
            "stale": cloud.heartbeat.stale(),
            "por_estado": {e: len(cloud.nodes.listar(estado=e)) for e in cloud.nodes.ESTADOS},
            "latencia_media_ms": round(sum(n.latencia_ms for n in nodos) / len(nodos), 2) if nodos else 0.0,
            "carga_media": round(sum(n.carga for n in nodos) / len(nodos), 3) if nodos else 0.0}


def metricas_regiones() -> dict:
    from src.platform import cloud
    salida = {}
    for r in cloud.REGIONES:
        ns = cloud.nodes.listar(region=r)
        if ns:
            salida[r] = {"nodos": len(ns),
                         "carga_media": round(sum(n.carga for n in ns) / len(ns), 3)}
    return salida


def metricas_clusteres() -> list:
    from src.platform import cloud
    return cloud.cluster.listar_clusters()


def _base_enterprise() -> dict:
    try:
        from src.services.observabilidad import metricas
        if hasattr(metricas, "snapshot"):
            return metricas.snapshot()
        if hasattr(metricas, "resumen"):
            return metricas.resumen()
    except Exception:
        pass
    return {}


def dashboard(nombre) -> dict:
    """Datos de un dashboard cloud. Nodos/regiones/clústeres se agregan aquí; el resto reutiliza las
    métricas Enterprise (gateways/apis/eventbus/scheduler/workflow/ccp)."""
    if nombre == "nodos":
        return {"dashboard": "nodos", **metricas_nodos()}
    if nombre == "regiones":
        return {"dashboard": "regiones", "regiones": metricas_regiones()}
    if nombre == "clusteres":
        return {"dashboard": "clusteres", "clusteres": metricas_clusteres()}
    if nombre in DASHBOARDS:
        return {"dashboard": nombre, "fuente": "observabilidad.metricas", "base": _base_enterprise()}
    return {"dashboard": nombre, "error": "desconocido"}


def dashboards() -> list:
    return list(DASHBOARDS)


__all__ = ["DASHBOARDS", "metricas_nodos", "metricas_regiones", "metricas_clusteres",
           "dashboard", "dashboards"]
