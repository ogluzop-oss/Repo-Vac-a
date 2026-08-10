"""
Explicabilidad de la ejecucion (Paquete Enterprise 10, SUBFASE 10.7). Antes de ejecutar, el sistema
explica: que hara, por que, que modulos afectara, que riesgos existen, que servicios participan y
el nivel de confianza. Reutiliza el detalle del plan y el simulador de origen; no recalcula.
"""

SERVICIOS = ["ExecutiveActionService", "Workflow/BPM", "Gobierno Corporativo", "AutomationService",
             "SimulationService", "DigitalTwinService", "PredictionService"]

# Modulo afectado por cada codigo de accion (informativo, para "que modulos afectara").
_MODULO = {
    "crear_tarea": "Centro de Actividad", "crear_recordatorio": "Calendario",
    "crear_incidencia": "Incidencias/SAT", "notificar": "Notificaciones",
    "solicitar_inventario": "Inventario", "solicitar_auditoria": "Contabilidad",
    "solicitar_revision": "Documentos", "proponer_liquidacion": "Etiquetas/Precios",
    "crear_propuesta_compra": "Compras", "solicitar_aprobacion": "Workflow",
    "modificar_precio": "Etiquetas/Precios", "generar_pedido": "Compras",
    "emitir_factura": "Facturacion", "realizar_pago": "Tesoreria",
    "mover_stock": "Inventario/Kardex", "despedir_empleado": "RRHH",
}


def explicar(detalle_plan) -> dict:
    acciones = []
    modulos = set()
    for fase, items in (detalle_plan.get("fases") or {}).items():
        for it in items:
            acciones.append({"fase": fase, "titulo": it.get("titulo"), "codigo": it.get("codigo"),
                             "critica": it.get("critica")})
            modulos.add(_MODULO.get(it.get("codigo"), "General"))
    return {
        "que_hara": [a["titulo"] for a in acciones],
        "por_que": detalle_plan.get("impacto", ""),
        "modulos_afectados": sorted(modulos),
        "riesgos": {"nivel": detalle_plan.get("riesgo", "BAJO"),
                    "acciones_criticas": detalle_plan.get("acciones_criticas", [])},
        "servicios_participantes": SERVICIOS,
        "nivel_confianza": detalle_plan.get("confianza", "MEDIA"),
        "responsables": detalle_plan.get("responsables", []),
        "tiempo_estimado_min": detalle_plan.get("tiempo_estimado_min", 0),
        "aviso": ("La IA propone; la organizacion decide. Nada se ejecuta sin plan APROBADO y "
                  "autorizacion valida. Las acciones criticas solo se proponen."),
    }
