"""
Catalogo de ACCIONES inteligentes reutilizables (Paquete Enterprise 4, SUBFASE 4.5).

Cada accion DELEGA en un subsistema existente (notificaciones, Workflow/BPM, propuestas de
reposicion...). NO se programa logica especifica ni se hacen escrituras criticas directas:
las propuestas son propuestas, las aprobaciones pasan por Workflow, las tareas son
notificaciones del Centro. Cada accion devuelve un texto de resultado (para la auditoria).
"""

import logging

logger = logging.getLogger("automatizacion.acciones")

_PRIO = {"CRITICA": "critica", "ALTA": "alta", "MEDIA": "normal", "BAJA": "baja",
         "INFORMATIVA": "baja"}


def _emitir(tipo, titulo, mensaje, *, modulo, prioridad="MEDIA", id_empresa=None,
            ref_entidad=None, ref_id=None):
    try:
        from src.services import notificaciones as N
        N.emitir(tipo, titulo, mensaje, prioridad=_PRIO.get(str(prioridad).upper(), "normal"),
                 modulo=modulo, roles=["ADMINISTRADOR", "GERENTE"], ref_entidad=ref_entidad,
                 ref_id=ref_id, id_empresa=id_empresa)
        return f"Notificacion emitida ({modulo})"
    except Exception as e:
        logger.debug("emitir: %s", e)
        return f"aviso: {titulo}"


def notificar(ctx, params, id_empresa=None) -> str:
    p = params or {}
    return _emitir("automatizacion", p.get("titulo", "Aviso automatico"),
                   ctx.get("mensaje", p.get("mensaje", "")), modulo=p.get("modulo", "automatizacion"),
                   prioridad=ctx.get("prioridad", "MEDIA"), id_empresa=id_empresa)


def crear_tarea(ctx, params, id_empresa=None) -> str:
    p = params or {}
    n = ctx.get("n", "")
    return _emitir("tarea", p.get("titulo", "Tarea automatica"),
                   f"{p.get('titulo', 'Tarea')} — {n} elemento(s) requieren atencion.",
                   modulo=p.get("modulo", "workflow"), prioridad=ctx.get("prioridad", "MEDIA"),
                   id_empresa=id_empresa)


def crear_recordatorio(ctx, params, id_empresa=None) -> str:
    p = params or {}
    return _emitir("recordatorio", p.get("titulo", "Recordatorio"), ctx.get("mensaje", ""),
                   modulo=p.get("modulo", "calendario"), prioridad="BAJA", id_empresa=id_empresa)


def crear_incidencia(ctx, params, id_empresa=None) -> str:
    p = params or {}
    return _emitir("incidencia", p.get("titulo", "Incidencia automatica"), ctx.get("mensaje", ""),
                   modulo="incidencias", prioridad=ctx.get("prioridad", "ALTA"), id_empresa=id_empresa)


def solicitar_aprobacion(ctx, params, id_empresa=None) -> str:
    """Lanza el circuito Workflow/BPM de aprobacion existente (no crea uno nuevo)."""
    p = params or {}
    entidad = p.get("entidad", "automatizacion")
    entidad_id = ctx.get("ref_id") or p.get("entidad_id") or "auto"
    try:
        from src.services.workflow import workflow_engine as WF
        r = WF.iniciar_proceso(entidad, entidad_id, contexto=ctx, id_empresa=id_empresa)
        return f"Workflow: {r.get('estado', 'iniciado')} (instancia {r.get('instancia')})"
    except Exception as e:
        logger.debug("solicitar_aprobacion: %s", e)
        return _emitir("aprobacion", p.get("titulo", "Aprobacion requerida"), "", modulo="workflow",
                       prioridad=ctx.get("prioridad", "ALTA"), id_empresa=id_empresa)


def crear_propuesta_compra(ctx, params, id_empresa=None) -> str:
    """Crea PROPUESTAS de reposicion (no pedidos reales) reutilizando reabastecimiento."""
    creadas = 0
    try:
        from src.db import reabastecimiento as R
        for a in (ctx.get("items") or [])[:20]:
            cod = a.get("codigo")
            if not cod:
                continue
            try:
                if not R.propuesta_pendiente_existe(cod, id_empresa):
                    R.crear_propuesta(cod, a.get("nombre") or cod, int(a.get("faltan") or 1),
                                      "AUTOMATIZACION", int(a.get("stock_tienda") or 0),
                                      int(a.get("objetivo") or 0), id_empresa=id_empresa)
                    creadas += 1
            except Exception:
                pass
    except Exception as e:
        logger.debug("crear_propuesta_compra: %s", e)
    _emitir("propuesta", "Propuestas de compra generadas",
            f"{creadas} propuestas de reposicion creadas automaticamente.", modulo="compras",
            prioridad="ALTA", id_empresa=id_empresa)
    return f"{creadas} propuestas de reposicion creadas"


def proponer_liquidacion(ctx, params, id_empresa=None) -> str:
    n = ctx.get("n", 0)
    return _emitir("propuesta", "Propuesta de liquidacion",
                   f"{n} productos sin ventas: se propone liquidacion/promocion.",
                   modulo="etiquetas", prioridad="BAJA", id_empresa=id_empresa)


def solicitar_inventario(ctx, params, id_empresa=None) -> str:
    return _emitir("tarea", "Solicitud de inventario", ctx.get("mensaje", ""), modulo="stock",
                   prioridad="MEDIA", id_empresa=id_empresa)


def solicitar_auditoria(ctx, params, id_empresa=None) -> str:
    return _emitir("tarea", "Solicitud de auditoria", ctx.get("mensaje", ""), modulo="contabilidad",
                   prioridad="MEDIA", id_empresa=id_empresa)


def solicitar_revision(ctx, params, id_empresa=None) -> str:
    return _emitir("tarea", "Solicitud de revision", ctx.get("mensaje", ""), modulo="documentos",
                   prioridad="MEDIA", id_empresa=id_empresa)


def enviar_correo(ctx, params, id_empresa=None) -> str:
    # Accion CRITICA (envio real): por defecto se propone como notificacion, no se envia auto.
    p = params or {}
    return _emitir("correo", p.get("titulo", "Correo propuesto"), ctx.get("mensaje", ""),
                   modulo="correo", prioridad=ctx.get("prioridad", "MEDIA"), id_empresa=id_empresa)


CATALOGO = {
    "notificar": notificar,
    "crear_tarea": crear_tarea,
    "crear_recordatorio": crear_recordatorio,
    "crear_incidencia": crear_incidencia,
    "solicitar_aprobacion": solicitar_aprobacion,
    "crear_propuesta_compra": crear_propuesta_compra,
    "proponer_liquidacion": proponer_liquidacion,
    "solicitar_inventario": solicitar_inventario,
    "solicitar_auditoria": solicitar_auditoria,
    "solicitar_revision": solicitar_revision,
    "enviar_correo": enviar_correo,
}


def ejecutar(codigo_accion, ctx, params, id_empresa=None) -> str:
    fn = CATALOGO.get(codigo_accion)
    if not fn:
        return f"accion desconocida: {codigo_accion}"
    try:
        return fn(ctx, params, id_empresa)
    except Exception as e:
        logger.error("accion %s: %s", codigo_accion, e)
        return f"error: {e}"


def registrar_accion(codigo, fn) -> None:
    """Amplia el catalogo de acciones sin tocar el motor."""
    CATALOGO[codigo] = fn
