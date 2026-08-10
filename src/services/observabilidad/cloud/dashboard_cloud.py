"""
Cloud Observability · Cloud Dashboard (Fase VI · Bloque 12). Panel unificado de observabilidad
distribuida que REUTILIZA la Observabilidad Enterprise + el Node Registry cloud: métricas por
nodos/regiones/clústeres, alertas cloud, logging centralizado y salud de la plataforma. Un único
punto de lectura; no crea un sistema de observabilidad paralelo.
"""

from __future__ import annotations

from src.services.observabilidad.cloud import alertas_cloud, log_collector, metricas_cloud


def panel() -> dict:
    """Snapshot completo del Cloud Dashboard."""
    salud_plataforma = {}
    try:
        from src.platform import health as ph
        salud_plataforma = ph.global_()
    except Exception:
        pass
    salud_nucleo = {}
    try:
        from src.services.observabilidad import health
        salud_nucleo = health.health()
    except Exception:
        pass
    return {
        "nodos": metricas_cloud.metricas_nodos(),
        "regiones": metricas_cloud.metricas_regiones(),
        "clusteres": metricas_cloud.metricas_clusteres(),
        "alertas": alertas_cloud.resumen(),
        "logs": log_collector.descriptor(),
        "salud_plataforma": salud_plataforma,
        "salud_nucleo": salud_nucleo,
        "dashboards": metricas_cloud.dashboards(),
    }


__all__ = ["panel"]
