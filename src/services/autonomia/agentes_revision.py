"""
Revision del plan por los agentes (Paquete Enterprise 10, SUBFASE 10.8). Antes de ejecutar, cada
agente especialista revisa el plan y emite: aprobado / observaciones / riesgos / recomendaciones.
Reutiliza el AgentManager existente; no crea agentes nuevos.
"""

import logging

logger = logging.getLogger("autonomia.agentes_revision")

# Codigo de accion → dominio de agente que la revisa.
_DOMINIO_ACCION = {
    "crear_propuesta_compra": "compras", "solicitar_inventario": "stock", "mover_stock": "stock",
    "generar_pedido": "compras", "modificar_precio": "ventas", "proponer_liquidacion": "ventas",
    "emitir_factura": "ventas", "realizar_pago": "financiero", "solicitar_auditoria": "auditoria",
    "despedir_empleado": "rrhh", "solicitar_aprobacion": "auditoria",
}


def revisar(detalle_plan, *, usuario=None, perfil="ADMINISTRADOR", id_empresa=None) -> list:
    """Cada agente implicado revisa su parte del plan. Devuelve una lista de dictamenes."""
    codigos = set()
    for items in (detalle_plan.get("fases") or {}).values():
        for it in items:
            codigos.add(it.get("codigo"))
    dominios = sorted({_DOMINIO_ACCION.get(cod, "auditoria") for cod in codigos})

    dictamenes = []
    try:
        from src.services.agentes import manager as _m
        mgr = _m()
        ctx = {"id_empresa": id_empresa, "usuario": usuario, "rol": perfil, "plan": detalle_plan}
        for dom in dominios:
            ag = mgr.delegar(dom, f"revisar plan {detalle_plan.get('id_plan')}", dict(ctx))
            if not ag:
                continue
            criticas_dom = [c for c in detalle_plan.get("acciones_criticas", [])]
            veredicto = "OBSERVACIONES" if criticas_dom else "APROBADO"
            dictamenes.append({
                "agente": ag.get("agente", dom), "dominio": dom, "veredicto": veredicto,
                "observaciones": ag.get("texto", ""),
                "riesgos": ag.get("predicciones", []) or ([f"Acciones criticas: {', '.join(criticas_dom)}"]
                                                          if criticas_dom else []),
                "recomendaciones": ag.get("fuentes", []),
            })
    except Exception as e:
        logger.debug("revisar agentes: %s", e)

    if not dictamenes:
        # Sin agentes disponibles: dictamen neutro basado en el propio plan.
        criticas = detalle_plan.get("acciones_criticas", [])
        dictamenes.append({"agente": "sistema", "dominio": "general",
                           "veredicto": "OBSERVACIONES" if criticas else "APROBADO",
                           "observaciones": ("Hay acciones criticas que requieren aprobacion."
                                             if criticas else "Plan de acciones seguras y reversibles."),
                           "riesgos": criticas, "recomendaciones": []})
    return dictamenes
