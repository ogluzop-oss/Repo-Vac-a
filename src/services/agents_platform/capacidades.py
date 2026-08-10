"""
AI Agents Platform · Capacidades (Fase V · Bloque 5). Cada capacidad de un agente DELEGA en la
infraestructura existente (nunca crea lógica paralela):

  consultar / analizar / proponer → Especialistas IA (`services.agentes.manager`)
  automatizar                     → Rules Engine (`services.rules`)
  generar_documento               → Documental
  iniciar_workflow / aprobacion   → Workflow Engine (`services.workflow`)
  enviar_comunicacion             → CCP (`services.ccp`)

Multiempresa (tenant en el contexto). Todo degradable.
"""

from __future__ import annotations

CAPACIDADES = ("consultar", "analizar", "proponer", "automatizar", "generar_documento",
               "iniciar_workflow", "enviar_comunicacion", "solicitar_aprobacion", "responder")


def _ctx(id_empresa, usuario):
    return {"id_empresa": id_empresa, "usuario": usuario or {}}


def consultar(dominio, consulta, *, id_empresa=None, usuario=None):
    try:
        from src.services.agentes import manager
        return manager().delegar(dominio, consulta, _ctx(id_empresa, usuario))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def analizar(dominio, consulta, *, id_empresa=None, usuario=None):
    return consultar(dominio, f"[análisis] {consulta}", id_empresa=id_empresa, usuario=usuario)


def proponer(dominio, *, id_empresa=None, usuario=None):
    try:
        from src.services.agentes import manager
        return manager().coordinar("¿qué debería hacer hoy?", _ctx(id_empresa, usuario),
                                   dominios=[dominio])
    except Exception as e:
        return {"ok": False, "error": str(e)}


def automatizar(regla, datos, *, id_empresa=None):
    try:
        from src.services import rules
        if hasattr(rules, "evaluar"):
            return rules.evaluar(regla, datos or {}, id_empresa=id_empresa)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "rules no disponible"}


def generar_documento(tipo, datos, *, id_empresa=None, usuario=None):
    try:
        from src.services import documental
        if hasattr(documental, "generar"):
            return documental.generar(tipo, datos or {}, id_empresa=id_empresa, usuario=usuario)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "documental no disponible", "tipo": tipo}


def iniciar_workflow(entidad, entidad_id, *, id_empresa=None, actor=None, contexto=None):
    try:
        from src.services.workflow import workflow_engine as wf
        return wf.iniciar_proceso(entidad, entidad_id, contexto=contexto, actor=actor,
                                  id_empresa=id_empresa)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def solicitar_aprobacion(entidad, entidad_id, *, id_empresa=None, actor=None, contexto=None):
    """Reutiliza el Workflow Engine para solicitar una aprobación (no un motor nuevo)."""
    return iniciar_workflow(entidad, entidad_id, id_empresa=id_empresa, actor=actor,
                            contexto={**(contexto or {}), "_motivo": "aprobacion_agente"})


def enviar_comunicacion(*, id_empresa=None, contexto=None, plantilla=None, pistas=None,
                        variables=None, usuario=None):
    try:
        from src.services import ccp
        r = ccp.enviar_comunicacion(id_empresa=id_empresa, pistas=pistas or {}, contexto=contexto,
                                    plantilla=plantilla, variables=variables or {}, usuario=usuario)
        return getattr(r, "__dict__", r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = ["CAPACIDADES", "consultar", "analizar", "proponer", "automatizar", "generar_documento",
           "iniciar_workflow", "solicitar_aprobacion", "enviar_comunicacion"]
