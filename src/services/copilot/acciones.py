"""
Acciones desde la conversacion (Paquete Enterprise 5, SUBFASE 5.6). El Copiloto NUNCA ejecuta
directamente: DELEGA en AutomationService/Workflow/BPM (propuestas y aprobaciones). Reutiliza el
catalogo de acciones del motor de automatizacion.
"""

import logging

logger = logging.getLogger("copilot.acciones")


def solicitar(cls, texto, ctx) -> dict:
    """Traduce una peticion en lenguaje natural a una accion ORQUESTADA (nunca ejecucion critica)."""
    t = (texto or "").lower()
    emp = ctx.get("id_empresa")
    ctxa = {"mensaje": texto, "prioridad": "MEDIA", "ref_id": ctx.get("usuario")}
    try:
        from src.services.automatizacion import acciones as A
    except Exception as e:
        logger.error("automatizacion no disponible: %s", e)
        return {"accion": "ninguna", "estado": "ERROR",
                "texto": "El motor de automatizacion no esta disponible.", "fuentes": []}

    if "aprob" in t:
        # SUBFASE 7.9: gobierno corporativo — ¿tiene el usuario autoridad para aprobar?
        try:
            import re as _re
            from src.services import gobierno
            m = _re.search(r"(\d[\d.]{2,})", (texto or "").replace(".", "").replace(",", "."))
            importe = float(m.group(1)) if m else 0
            entidad = ("factura" if "factura" in t else ("compras" if "compra" in t else "gasto"))
            g = gobierno.servicio().puede_aprobar(ctx.get("usuario"), entidad, importe,
                                                  ctx.get("id_empresa"), ctx.get("rol"))
            if not g.get("permitido"):
                return {"accion": "solicitar_aprobacion", "estado": "DENEGADA", "resultado": g["motivo"],
                        "texto": g["motivo"], "fuentes": ["Gobierno Corporativo", "Workflow/BPM"]}
        except Exception as e:
            logger.debug("gobierno puede_aprobar: %s", e)
        r = A.solicitar_aprobacion(ctxa, {"entidad": "copilot"}, emp)
        return {"accion": "solicitar_aprobacion", "estado": "PENDIENTE", "resultado": r,
                "texto": f"He solicitado la aprobacion via Workflow. {r}",
                "fuentes": ["Gobierno Corporativo", "Workflow/BPM"]}
    if "pedido" in t or "compra" in t or "reponer" in t:
        r = A.crear_propuesta_compra({"items": []}, None, emp)
        return {"accion": "crear_propuesta_compra", "estado": "PROPUESTA", "resultado": r,
                "texto": f"He preparado una propuesta de compra (pendiente de tu decision). {r}",
                "fuentes": ["AutomationService", "Compras"]}
    if "auditor" in t:
        r = A.solicitar_auditoria(ctxa, None, emp)
        return {"accion": "solicitar_auditoria", "estado": "PROPUESTA", "resultado": r,
                "texto": f"He programado la solicitud de auditoria. {r}", "fuentes": ["AutomationService"]}
    if "inventario" in t:
        r = A.solicitar_inventario(ctxa, None, emp)
        return {"accion": "solicitar_inventario", "estado": "PROPUESTA", "resultado": r,
                "texto": f"He preparado la solicitud de inventario. {r}", "fuentes": ["AutomationService"]}
    if "incidencia" in t:
        r = A.crear_incidencia(ctxa, {"titulo": "Incidencia (copiloto)"}, emp)
        return {"accion": "crear_incidencia", "estado": "PROPUESTA", "resultado": r,
                "texto": f"He abierto una incidencia. {r}", "fuentes": ["AutomationService"]}
    # Por defecto: crear tarea (propuesta, revisable en el Centro/Workflow).
    r = A.crear_tarea(ctxa, {"modulo": "workflow", "titulo": (texto or "Tarea")[:60]}, emp)
    return {"accion": "crear_tarea", "estado": "PROPUESTA", "resultado": r,
            "texto": f"He preparado la tarea (pendiente de tu revision). {r}",
            "fuentes": ["AutomationService", "Workflow"]}
