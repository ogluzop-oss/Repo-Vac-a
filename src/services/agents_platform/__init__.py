"""
AI Agents Platform (Fase V · Bloque 5) — fachada.

Evoluciona la IA hacia AGENTES ESPECIALIZADOS. No son asistentes aislados: cada agente reutiliza
IOC, CCP, Workflow, REST, Rules Engine, Scheduler y Event Bus (a través de `services.agentes` y las
capacidades transversales). Cada agente es un módulo independiente. Multiempresa.

    from src.services import agents_platform as ap
    a = ap.agente("ventas")
    a.consultar("¿cómo van las ventas?", id_empresa=emp)
    a.iniciar_workflow("pedido", 123, id_empresa=emp)
"""

from src.services.agents_platform.agente import AgentePlataforma  # noqa: F401
from src.services.agents_platform import capacidades  # noqa: F401

# Agentes iniciales (dominios). Cada uno es un módulo independiente sobre la misma infraestructura.
AGENTES = ("compras", "ventas", "rrhh", "fiscal", "inventario", "produccion", "logistica",
           "crm", "sat", "gmao", "calidad", "auditoria")

_INSTANCIAS = {}


def agente(dominio) -> AgentePlataforma:
    if dominio not in _INSTANCIAS:
        _INSTANCIAS[dominio] = AgentePlataforma(dominio)
    return _INSTANCIAS[dominio]


def listar() -> list:
    return [agente(d).descriptor() for d in AGENTES]


def panel() -> dict:
    """Panel de la plataforma de agentes (reutiliza el panel del AgentManager si está disponible)."""
    base = {"agentes": list(AGENTES), "capacidades": list(capacidades.CAPACIDADES)}
    try:
        from src.services.agentes import manager
        base["especialistas"] = manager().panel()
    except Exception:
        pass
    return base


__all__ = ["AGENTES", "AgentePlataforma", "capacidades", "agente", "listar", "panel"]
