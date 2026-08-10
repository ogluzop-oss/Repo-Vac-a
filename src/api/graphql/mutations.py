"""
GraphQL Enterprise · Mutations (Fase IV · Bloque 1). Resolvers de ESCRITURA. Reutilizan EXACTAMENTE
los servicios existentes (crear/editar/eliminar/activar/desactivar/ejecutar). Nunca SQL ni `src.db`.
El tenant sale del contexto; el servicio aplica la lógica, la validación y los eventos.
"""

from __future__ import annotations

from src.api.graphql import context as _c
from src.api.graphql import registry


def _emp(ctx):
    return _c.id_empresa(ctx)


def _usuario(ctx):
    return (_c.usuario(ctx) or {}).get("nombre") or (_c.usuario(ctx) or {}).get("id")


# ── Comunicaciones ─────────────────────────────────────────────────────────────
def _m_send_communication(ctx, contexto=None, plantilla=None, pistas=None, variables=None, **_):
    try:
        from src.services import ccp
        r = ccp.enviar_comunicacion(id_empresa=_emp(ctx), pistas=pistas or {},
                                    contexto=contexto, plantilla=plantilla,
                                    variables=variables or {}, usuario=_usuario(ctx))
        return getattr(r, "__dict__", r)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _m_create_campaign(ctx, nombre=None, tipo=None, **_):
    try:
        from src.services import ccp
        return ccp.campanas.crear_campana(id_empresa=_emp(ctx), nombre=nombre, tipo=tipo,
                                          usuario=_usuario(ctx))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _m_create_template(ctx, codigo=None, categoria=None, idioma="es", **_):
    try:
        from src.services import ccp
        return ccp.templates.crear_plantilla(id_empresa=_emp(ctx), codigo=codigo,
                                             categoria=categoria, idioma=idioma)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Marketplace / Plugins ──────────────────────────────────────────────────────
def _m_install_plugin(ctx, clave=None, origen=None, **_):
    try:
        from src.services import marketplace
        return marketplace.instalar(clave, id_empresa=_emp(ctx), origen=origen,
                                    usuario=_usuario(ctx))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _m_uninstall_plugin(ctx, clave=None, **_):
    try:
        from src.services import marketplace
        return marketplace.desinstalar(clave, id_empresa=_emp(ctx), usuario=_usuario(ctx))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _m_rollback_plugin(ctx, clave=None, **_):
    try:
        from src.services import marketplace
        return marketplace.rollback(clave, id_empresa=_emp(ctx), usuario=_usuario(ctx))
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Ejecuciones (scheduler / rules) ────────────────────────────────────────────
def _m_run_job(ctx, job=None, **_):
    try:
        from src.services import scheduler_enterprise as sch
        if hasattr(sch, "ejecutar_ahora"):
            return sch.ejecutar_ahora(job, id_empresa=_emp(ctx))
        return {"ok": False, "error": "no disponible"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _m_run_rule(ctx, regla=None, datos=None, **_):
    try:
        from src.services import rules
        if hasattr(rules, "evaluar"):
            return rules.evaluar(regla, datos or {}, id_empresa=_emp(ctx))
        return {"ok": False, "error": "no disponible"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def registrar_todo():
    M = registry.registrar_mutation
    M("sendCommunication", _m_send_communication, tipo="Result",
      args={"contexto": "String", "plantilla": "String", "pistas": "JSON", "variables": "JSON"},
      servicio="ccp.enviar_comunicacion", permiso="comunicaciones.enviar")
    M("createCampaign", _m_create_campaign, tipo="Campaign",
      args={"nombre": "String!", "tipo": "String"}, servicio="ccp.campanas.crear_campana",
      permiso="comunicaciones.gestionar")
    M("createTemplate", _m_create_template, tipo="Template",
      args={"codigo": "String!", "categoria": "String", "idioma": "String"},
      servicio="ccp.templates.crear_plantilla", permiso="comunicaciones.gestionar")
    M("installPlugin", _m_install_plugin, tipo="Result",
      args={"clave": "String!", "origen": "String"}, servicio="marketplace.instalar",
      permiso="marketplace.gestionar")
    M("uninstallPlugin", _m_uninstall_plugin, tipo="Result", args={"clave": "String!"},
      servicio="marketplace.desinstalar", permiso="marketplace.gestionar")
    M("rollbackPlugin", _m_rollback_plugin, tipo="Result", args={"clave": "String!"},
      servicio="marketplace.rollback", permiso="marketplace.gestionar")
    M("runJob", _m_run_job, tipo="Result", args={"job": "String!"},
      servicio="scheduler_enterprise.ejecutar_ahora", permiso="scheduler.ejecutar")
    M("runRule", _m_run_rule, tipo="Result", args={"regla": "String!", "datos": "JSON"},
      servicio="rules.evaluar", permiso="rules.ejecutar")


__all__ = ["registrar_todo"]
