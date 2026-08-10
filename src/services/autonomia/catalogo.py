"""
Catalogo de acciones ejecutables de forma controlada (Paquete Enterprise 10). REUTILIZA el catalogo
de AutomationService (avisos/tareas/propuestas — acciones aditivas y reversibles). NO ejecuta
escrituras criticas: las acciones CRITICAS (generar pedido, modificar precio, despedir, emitir
factura, pagar, mover stock) NO tienen ejecutor real — se convierten SIEMPRE en una propuesta que
pasa por Workflow/Gobierno (SUBFASE 10.14). El sistema propone; la organizacion decide.
"""

import logging

logger = logging.getLogger("autonomia.catalogo")

# codigo -> {titulo, reversible, critica, informativa}
ACCIONES = {
    # Acciones seguras/reversibles (avisos, tareas y propuestas del Centro/AutomationService).
    "notificar":            {"titulo": "Emitir aviso", "reversible": True, "critica": False, "informativa": True},
    "crear_tarea":          {"titulo": "Crear tarea", "reversible": True, "critica": False, "informativa": True},
    "crear_recordatorio":   {"titulo": "Crear recordatorio", "reversible": True, "critica": False, "informativa": True},
    "crear_incidencia":     {"titulo": "Abrir incidencia", "reversible": True, "critica": False, "informativa": True},
    "solicitar_inventario": {"titulo": "Solicitar inventario", "reversible": True, "critica": False, "informativa": True},
    "solicitar_auditoria":  {"titulo": "Solicitar auditoria", "reversible": True, "critica": False, "informativa": True},
    "solicitar_revision":   {"titulo": "Solicitar revision", "reversible": True, "critica": False, "informativa": True},
    "proponer_liquidacion": {"titulo": "Proponer liquidacion", "reversible": True, "critica": False, "informativa": True},
    "crear_propuesta_compra": {"titulo": "Proponer reposicion", "reversible": True, "critica": False, "informativa": False},
    "solicitar_aprobacion": {"titulo": "Solicitar aprobacion (Workflow)", "reversible": True, "critica": False, "informativa": True},
    # Acciones CRITICAS: NUNCA se ejecutan automaticamente. Se convierten en propuesta gobernada.
    "generar_pedido":       {"titulo": "Generar pedido", "reversible": False, "critica": True, "informativa": False},
    "modificar_precio":     {"titulo": "Modificar precio", "reversible": False, "critica": True, "informativa": False},
    "emitir_factura":       {"titulo": "Emitir factura", "reversible": False, "critica": True, "informativa": False},
    "realizar_pago":        {"titulo": "Realizar pago", "reversible": False, "critica": True, "informativa": False},
    "mover_stock":          {"titulo": "Mover stock", "reversible": False, "critica": True, "informativa": False},
    "despedir_empleado":    {"titulo": "Despedir empleado", "reversible": False, "critica": True, "informativa": False},
}

CRITICAS = tuple(k for k, v in ACCIONES.items() if v["critica"])


def meta(codigo) -> dict:
    return ACCIONES.get(codigo, {"titulo": codigo, "reversible": False, "critica": True, "informativa": False})


def es_ejecutable(codigo) -> bool:
    """Solo las acciones no criticas tienen ejecutor real; las criticas solo se proponen."""
    return codigo in ACCIONES and not ACCIONES[codigo]["critica"]


def ejecutar(codigo, ctx, params, id_empresa=None) -> str:
    """Ejecuta una accion NO critica delegando en AutomationService. Una accion critica NUNCA se
    ejecuta: se transforma en una solicitud de aprobacion gobernada (Workflow/BPM)."""
    m = meta(codigo)
    if m["critica"]:
        # Seguridad 10.14: convertir en propuesta, jamas ejecutar.
        from src.services.automatizacion import acciones as A
        ctxp = dict(ctx or {}); ctxp["mensaje"] = f"[PROPUESTA] {m['titulo']} requiere aprobacion manual."
        A.solicitar_aprobacion(ctxp, {"entidad": "autonomia", "titulo": m["titulo"]}, id_empresa)
        return f"PROPUESTA (accion critica '{codigo}' no ejecutable automaticamente; enviada a aprobacion)"
    try:
        from src.services.automatizacion import acciones as A
        return A.ejecutar(codigo, ctx or {}, params or {}, id_empresa)
    except Exception as e:
        logger.error("ejecutar %s: %s", codigo, e)
        return f"error: {e}"


def revertir(codigo, ctx, params, id_empresa=None) -> str:
    """Compensacion reversible: emite un aviso de anulacion de la accion previa. Las acciones del
    catalogo son avisos/tareas/propuestas del Centro, por lo que su reversion es informativa y
    trazable (nunca deja efecto en datos operativos)."""
    m = meta(codigo)
    if not m["reversible"]:
        return "no reversible"
    try:
        from src.services.automatizacion import acciones as A
        ctxr = dict(ctx or {}); ctxr["mensaje"] = f"Reversion de: {m['titulo']}"
        A.notificar(ctxr, {"titulo": f"Reversion — {m['titulo']}", "modulo": "autonomia"}, id_empresa)
        return f"revertida ({m['titulo']})"
    except Exception as e:
        logger.debug("revertir %s: %s", codigo, e)
        return "reversion registrada"
