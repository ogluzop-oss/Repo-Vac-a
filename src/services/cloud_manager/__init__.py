"""
Multi-Tenant Cloud Manager (Fase V · Bloque 7) — fachada.

Panel maestro para administrar TODAS las empresas SaaS. REUTILIZA SaaS (licensing/planes/métricas/
backup), Observabilidad, la plataforma (registry/health) y el dominio de empresas. No crea segundos
motores. Solo SUPERADMIN. Vista global: empresas · usuarios · consumo · API · CCP · Workflow · IA ·
Plugins · Marketplace · Scheduler · Observabilidad.

    from src.services import cloud_manager as cm
    cm.tenants.listar()
    cm.monitorizacion.global_()
    cm.vista_global()
"""

from src.services.cloud_manager import tenants, licencias_cloud, monitorizacion  # noqa: F401


def vista_global() -> dict:
    """Agrega el estado de toda la plataforma SaaS reutilizando los servicios existentes."""
    empresas = tenants.listar()
    monit = monitorizacion.global_()
    plataforma = {}
    try:
        from src import platform as plat
        if not plat.registry.nombres():
            plat.bootstrap()
        plataforma = {"servicios": plat.registry.nombres(),
                      "salud": plat.health.global_().get("estado")}
    except Exception:
        pass
    marketplace = {}
    try:
        from src.services import marketplace as mk
        marketplace = {"catalogo": len(mk.catalogo(None))}
    except Exception:
        pass
    return {"empresas": len(empresas), "detalle_empresas": empresas,
            "planes": list(licencias_cloud.PLANES), "monitorizacion": monit,
            "plataforma": plataforma, "marketplace": marketplace}


__all__ = ["tenants", "licencias_cloud", "monitorizacion", "vista_global"]
