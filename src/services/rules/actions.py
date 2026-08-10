"""
Acciones del Rules Engine (Fase III · B5) — ejecuta acciones reutilizando la infraestructura.

Cada acción es un dict {tipo, ...}. Toda la ejecución pasa por los servicios existentes (CCP, Event Bus,
notificaciones, workflow): el motor NO implementa lógica de negocio, solo orquesta. Multiempresa.
"""

import logging

logger = logging.getLogger("rules.actions")


def ejecutar(accion, contexto, *, id_empresa=None) -> dict:
    """Ejecuta una acción y devuelve {tipo, ok, detalle}. `contexto` aporta datos (destinatario…)."""
    t = accion.get("tipo")
    ctx = contexto or {}
    try:
        if t == "enviar_comunicacion":
            from src.services import ccp
            res = ccp.enviar_comunicacion(
                id_empresa=id_empresa, destinatario=accion.get("destinatario") or ctx.get("correo"),
                pistas=accion.get("pistas"), asunto=accion.get("asunto", ""),
                cuerpo=accion.get("cuerpo", ""), plantilla=accion.get("plantilla"),
                canal=accion.get("canal"), contexto=accion.get("contexto") or "rules")
            return {"tipo": t, "ok": res.ok, "detalle": res.com_id}
        if t == "lanzar_evento":
            from src.services import eventbus
            ev = eventbus.publish(accion.get("evento", "RuleEvent"), id_empresa=id_empresa,
                                  ref_entidad=ctx.get("entidad"), ref_id=ctx.get("id"),
                                  payload={**ctx, **accion.get("payload", {})})
            return {"tipo": t, "ok": bool(ev), "detalle": (ev or {}).get("id")}
        if t in ("notificar", "crear_incidencia", "crear_alerta"):
            from src.services import notificaciones
            tipo_n = "incidencia" if t == "crear_incidencia" else ("alerta" if t == "crear_alerta"
                                                                   else "aviso")
            nid = notificaciones.emitir(tipo_n, accion.get("titulo", "Regla"),
                                        accion.get("mensaje", ""), prioridad=accion.get("prioridad",
                                        "normal"), modulo="rules", roles=accion.get("roles"),
                                        usuarios=accion.get("usuarios"), id_empresa=id_empresa)
            return {"tipo": t, "ok": bool(nid), "detalle": nid}
        if t == "crear_workflow":
            from src.services import ccp
            r = ccp.workflows.ejecutar_flujo(accion.get("flujo"), ctx, id_empresa=id_empresa,
                                             destinatario=accion.get("destinatario") or ctx.get("correo"),
                                             simular_esperas=False)
            return {"tipo": t, "ok": bool(r.get("ok")), "detalle": r.get("detenido_en")}
        if t in ("cambiar_prioridad", "actualizar_estado"):
            # Acciones observacionales: se registran como evento (el módulo destino reacciona).
            from src.services import eventbus
            eventbus.publish("RuleStateChange", id_empresa=id_empresa,
                             payload={"accion": t, **accion, **ctx})
            return {"tipo": t, "ok": True, "detalle": accion.get("valor")}
        return {"tipo": t, "ok": False, "detalle": "acción desconocida"}
    except Exception as e:
        logger.debug("acción %s: %s", t, e)
        return {"tipo": t, "ok": False, "detalle": str(e)}
