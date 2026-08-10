"""
Garantia de seguridad del simulador (Paquete Enterprise 9, SUBFASE 9.16).

Una simulacion NUNCA puede: generar pedidos, generar facturas, modificar stock, cambiar contratos
ni enviar correos. Todo permanece VIRTUAL. Esta garantia es estructural: el simulador solo lee del
Gemelo Digital/PredictionService y solo escribe en sus propias tablas `sim_*` (escenarios/variables/
resultados). Este modulo documenta y hace explicita esa frontera.
"""

# Acciones que el simulador tiene TERMINANTEMENTE PROHIBIDO ejecutar.
ACCIONES_PROHIBIDAS = (
    "generar_pedido", "generar_factura", "modificar_stock", "cambiar_contrato",
    "enviar_correo", "publicar_precio", "ejecutar_workflow", "crear_asiento",
)

# Tablas en las que el simulador SI puede escribir (todo virtual, borrable sin efecto real).
TABLAS_PERMITIDAS = ("sim_escenarios", "sim_variables", "sim_resultados")


def es_virtual() -> bool:
    """El simulador es virtual por construccion (no tiene rutas de escritura a produccion)."""
    return True


def garantia() -> dict:
    return {
        "virtual": True,
        "acciones_prohibidas": list(ACCIONES_PROHIBIDAS),
        "tablas_escritura_permitidas": list(TABLAS_PERMITIDAS),
        "descripcion": ("El simulador solo LEE del Gemelo Digital y PredictionService, y solo "
                        "escribe en tablas sim_* (escenarios virtuales). No existe ninguna ruta de "
                        "escritura hacia datos operativos, ni envio de comunicaciones."),
    }
