"""
Enterprise Platform Capabilities (RFC-CD-002 · enmienda ratificada) — ÚNICO punto de dependencia de
la Plataforma de Comercio Digital hacia la infraestructura Enterprise.

La PCD conoce CAPACIDADES, nunca implementaciones concretas (Workflow/Rules/CCP/IA/…). Así se puede
sustituir cualquier motor —incluido el proveedor de IA (N10/I9)— sin tocar la PCD. Degradable: si una
capacidad no está disponible, `obtener` devuelve None y el llamador degrada con elegancia.

    from src.platform import capabilities as cap
    cap.eventbus().publish(...)          # nunca `from src.services import eventbus`
    cap.workflow().iniciar_proceso(...)
    if cap.disponible("ia"): ...
"""

from __future__ import annotations

import importlib

# capacidad → módulo Enterprise que la provee (import perezoso, desacoplado).
_PROVIDERS = {
    "eventbus": "src.services.eventbus",
    "workflow": "src.services.workflow.workflow_engine",
    "rules": "src.services.rules",
    "scheduler": "src.services.scheduler_enterprise",
    "ccp": "src.services.ccp",
    "ia": "src.services.agents_platform",
    "observabilidad": "src.services.observabilidad",
    "rbac": "src.services.autorizacion",
    "marketplace": "src.services.marketplace",
    "saas_global": "src.services.saas_global",
    "storage": "src.platform.cloud.storage",
    "documental": "src.db.documentos",
    "pagos": "src.services.tpv.pagos",
    "secret_manager": "src.services.seguridad.secret_manager",
    "divisas": "src.utils.divisas",
    "fiscalidad": "src.utils.fiscalidad",
    "inteligencia": "src.services.inteligencia",
}


def obtener(nombre):
    """Handle de una capacidad, o None si no está disponible (degradable)."""
    ruta = _PROVIDERS.get(nombre)
    if not ruta:
        return None
    try:
        return importlib.import_module(ruta)
    except Exception:
        return None


def disponible(nombre) -> bool:
    return obtener(nombre) is not None


def capacidades() -> list:
    return sorted(_PROVIDERS)


def descriptor() -> dict:
    return {"capacidades": capacidades(),
            "disponibles": [n for n in _PROVIDERS if disponible(n)]}


# ── accesos de conveniencia (la PCD llama a estos, no a los módulos) ──────────
def eventbus():        return obtener("eventbus")        # noqa: E704
def workflow():        return obtener("workflow")        # noqa: E704
def rules():           return obtener("rules")           # noqa: E704
def scheduler():       return obtener("scheduler")       # noqa: E704
def ccp():             return obtener("ccp")             # noqa: E704
def ia():              return obtener("ia")              # noqa: E704
def observabilidad():  return obtener("observabilidad")  # noqa: E704
def rbac():            return obtener("rbac")            # noqa: E704
def marketplace():     return obtener("marketplace")     # noqa: E704
def saas_global():     return obtener("saas_global")     # noqa: E704
def storage():         return obtener("storage")         # noqa: E704
def documental():      return obtener("documental")      # noqa: E704
def pagos():           return obtener("pagos")           # noqa: E704
def secret_manager():  return obtener("secret_manager")  # noqa: E704
def divisas():         return obtener("divisas")         # noqa: E704
def fiscalidad():      return obtener("fiscalidad")      # noqa: E704
def inteligencia():    return obtener("inteligencia")    # noqa: E704


__all__ = ["obtener", "disponible", "capacidades", "descriptor", "eventbus", "workflow", "rules",
           "scheduler", "ccp", "ia", "observabilidad", "rbac", "marketplace", "saas_global",
           "storage", "documental", "pagos", "secret_manager", "divisas", "fiscalidad",
           "inteligencia"]
