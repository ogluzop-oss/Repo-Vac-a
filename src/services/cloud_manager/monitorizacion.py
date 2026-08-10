"""
Cloud Manager · Monitorización (Fase V · Bloque 7). Consumo y salud por empresa y global,
REUTILIZANDO SaaS métricas (`services.saas.metricas`) y Observabilidad (`services.observabilidad`).
Recursos de sistema (CPU/RAM/almacenamiento) vía psutil si está disponible (degradable). No crea un
segundo sistema de métricas.
"""

from __future__ import annotations


def sistema() -> dict:
    """CPU/RAM/almacenamiento del host (degradable: N/A si no hay psutil)."""
    try:
        import psutil
        return {"cpu_pct": psutil.cpu_percent(interval=None),
                "ram_pct": psutil.virtual_memory().percent,
                "disco_pct": psutil.disk_usage(".").percent}
    except Exception:
        return {"cpu_pct": None, "ram_pct": None, "disco_pct": None, "nota": "psutil no disponible"}


def salud() -> dict:
    try:
        from src.services.observabilidad import health
        return health.health()
    except Exception:
        return {"status": "unknown"}


def consumo(id_empresa) -> dict:
    """Consumo de una empresa (reutiliza SaaS métricas) + uso API/IA/CCP si está disponible."""
    datos = {}
    try:
        from src.services.saas import metricas
        datos["saas"] = metricas.consumo_empresa(id_empresa)
    except Exception:
        datos["saas"] = {}
    return {"id_empresa": id_empresa, **datos}


def global_() -> dict:
    """Métricas globales del clúster SaaS (empresas, eventos, errores, latencia…)."""
    resumen = {}
    try:
        from src.services.saas import metricas
        resumen = metricas.resumen()
    except Exception:
        pass
    try:
        from src.platform import health as ph
        plataforma = ph.global_()
    except Exception:
        plataforma = {}
    return {"saas": resumen, "sistema": sistema(), "salud": salud(),
            "plataforma": plataforma}


__all__ = ["sistema", "salud", "consumo", "global_"]
