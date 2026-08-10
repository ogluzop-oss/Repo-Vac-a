"""
Plataforma (Fase IV · Bloque 3) — Preparación para MICROSERVICIOS. Fachada única.

NO divide el ERP: prepara la arquitectura para que CUALQUIER subsistema pueda convertirse en un
microservicio independiente sin rediseñar la app. Reúne Service Registry + Discovery + Health +
Heartbeat + Routing + Gateway + Versioning + Contracts. Todo en proceso hoy; distribuible mañana
con el MISMO contrato. Los eventos SIEMPRE viajan por el Corporate Event Bus (nunca un bus paralelo).

    from src import platform as plat
    plat.bootstrap()                 # auto-registra los subsistemas existentes
    plat.health.global_()            # salud agregada
    plat.discovery.por_capacidad("comunicaciones")
"""

from __future__ import annotations

from src.platform import contracts, discovery, gateway, health, heartbeat, registry, routing, versioning
from src.platform.contracts import ServiceContract

PLATFORM_VERSION = "4.0.0"

# Catálogo declarativo de los subsistemas EXISTENTES (nombre, versión, capacidades, transportes,
# dependencias, rutas). Es el mapa de servicios auto-registrables — sin tocar dichos módulos.
_SUBSISTEMAS = [
    ("ioc", "1.0.0", ("identidad", "centros"), ("rest",), (), ("/identidad",)),
    ("ccp", "2.0.0", ("comunicaciones", "campañas", "plantillas", "timeline"),
     ("rest", "graphql", "eventbus"), ("ioc",), ("/communications", "/campaigns", "/templates")),
    ("rest_api", "1.0.0", ("api",), ("rest",), ("ccp",), ("/api",)),
    ("graphql", "1.0.0", ("api", "consulta"), ("graphql",), ("ccp", "rest_api"), ("/graphql",)),
    ("scheduler", "1.0.0", ("jobs", "cron"), ("rest", "eventbus"), (), ("/scheduler",)),
    ("workflow", "1.0.0", ("aprobaciones",), ("rest", "eventbus"), (), ("/workflow",)),
    ("rules", "1.0.0", ("reglas",), ("rest", "eventbus"), (), ("/rules",)),
    ("observability", "1.0.0", ("salud", "metricas", "trazas"), ("rest",), (), ("/health", "/metrics")),
    ("eventbus", "1.0.0", ("eventos",), ("eventbus",), (), ()),
    ("marketplace", "1.0.0", ("plugins", "catalogo"), ("rest", "eventbus"), ("eventbus",),
     ("/marketplace",)),
    ("ia", "1.0.0", ("ia", "copilot"), ("rest",), (), ("/ia",)),
    ("bi", "1.0.0", ("kpis", "dw"), ("rest",), (), ("/bi", "/kpis")),
    ("audit_replay", "1.0.0", ("auditoria",), ("rest",), ("eventbus",), ("/audit",)),
    # Fase V
    ("mobile", "1.0.0", ("movil", "offline"), ("rest",), ("rest_api",), ("/mobile",)),
    ("portal", "1.0.0", ("portal_web",), ("rest", "graphql"), ("rest_api", "graphql"), ("/portal",)),
    ("api_publica", "1.0.0", ("developers", "oauth"), ("rest",), ("rest_api",), ("/oauth", "/dev")),
    ("bpd", "1.0.0", ("procesos", "diseñador"), ("rest",), ("workflow",), ("/bpd",)),
    ("agents_platform", "1.0.0", ("agentes_ia",), ("rest", "eventbus"),
     ("ccp", "workflow", "rules"), ("/agents",)),
    ("datalake", "1.0.0", ("data_lake", "bi"), ("rest",), ("bi",), ("/datalake", "/bi")),
    ("cloud_manager", "1.0.0", ("saas_admin", "multitenant"), ("rest",),
     ("observability",), ("/cloud",)),
    # Fase VI
    ("cloud", "1.0.0", ("distribuido", "nodos", "clusters"), ("rest",), (), ("/cluster",)),
    ("observability_cloud", "1.0.0", ("observabilidad_cloud", "tracing", "logs"), ("rest",),
     ("observability",), ("/obs-cloud",)),
    ("saas_global", "1.0.0", ("multiregion", "planes_global", "feature_flags"), ("rest",),
     ("cloud_manager",), ("/global",)),
]


def _health_de(nombre):
    """Devuelve el callable de health del subsistema (reutiliza el existente cuando lo hay)."""
    if nombre == "observability":
        try:
            from src.services.observabilidad import health as _h
            return _h.health
        except Exception:
            return None
    if nombre in ("rest_api", "graphql", "ccp"):
        try:
            from src.services.observabilidad import health as _h
            return _h.ready
        except Exception:
            return None
    return None


def bootstrap() -> int:
    """Registra (idempotente) los subsistemas existentes en el Service Registry. Nº registrados."""
    n = 0
    for nombre, ver, caps, trans, deps, rutas in _SUBSISTEMAS:
        c = ServiceContract(nombre=nombre, version=ver, capacidades=caps, transportes=trans,
                            dependencias=deps, rutas=rutas, health=_health_de(nombre))
        if registry.registrar(c):
            n += 1
    # Los servicios de dominio (p. ej. la Plataforma de Comercio Digital) DECLARAN sus contratos;
    # la Enterprise Platform los REGISTRA (aislamiento del Service Registry — la PCD no lo toca).
    try:
        from src.services.comercio_digital import contratos as _cd_contratos
        for c in _cd_contratos():
            if registry.registrar(c):
                n += 1
    except Exception:
        pass
    return n


__all__ = ["PLATFORM_VERSION", "bootstrap", "contracts", "discovery", "gateway", "health",
           "heartbeat", "registry", "routing", "versioning", "ServiceContract"]
