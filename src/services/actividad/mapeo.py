"""
Mapeo del Centro de Actividad (Fase 3): tipo de evento → tarjeta del menu (v_id) y
prioridades que generan badge.

SUBFASE 3.4: no todo genera badge. Solo CRITICA/ALTA/MEDIA (los importantes). BAJA e
INFORMATIVA aparecen en el timeline pero NO ponen circulo rojo.
"""

# tipo de evento (Fase 1/2) → identificador de tarjeta del menu principal.
TIPO_A_VID = {
    # Etiquetas / precios / promociones
    "PRECIO_ACTUALIZADO": "etiquetas", "PROMOCION_PUBLICADA": "etiquetas",
    "PROMOCION_FINALIZADA": "etiquetas",
    # Catalogo
    "ARTICULO_CREADO": "catalogo", "ARTICULO_MODIFICADO": "catalogo",
    "ARTICULO_ELIMINADO": "catalogo",
    # CRM
    "CLIENTE_CREADO": "clientes_crm", "CLIENTE_MODIFICADO": "clientes_crm",
    # Compras / proveedores
    "PROVEEDOR_ACTUALIZADO": "compras", "PEDIDO_RECIBIDO": "compras",
    # Ventas / facturacion
    "FACTURA_GENERADA": "ventas", "FACTURA_ANULADA": "ventas",
    "FACTURA_RECTIFICADA": "ventas", "VENTA_REGISTRADA": "ventas",
    # Tesoreria
    "COBRO_REGISTRADO": "tesoreria",
    # Documentos
    "DOCUMENTO_PUBLICADO": "documentos",
    # Seguridad
    "USUARIO_CREADO": "seguridad", "USUARIO_BLOQUEADO": "seguridad",
    "ROL_MODIFICADO": "seguridad",
    # RRHH
    "CONTRATO_GENERADO": "rrhh", "NOMINA_GENERADA": "rrhh",
    "BAJA_REGISTRADA": "horarios",
    # Inventario / stock / logistica
    "INVENTARIO_CORREGIDO": "stock", "KARDEX_MOVIMIENTO": "stock",
    "MERMA_REGISTRADA": "mermas", "REPOSICION_GENERADA": "reposicion",
    "UBICACION_ASIGNADA": "ubicacion",
    # Correo
    "CORREO_RECIBIDO": "correo", "CORREO_ENVIADO": "correo",
    # Workflow / contabilidad / BI
    "WORKFLOW_INICIADO": "workflow", "ASIENTO_CONTABILIZADO": "contabilidad",
    "BI_SNAPSHOT_GENERADO": "bi",
}

# Prioridades que ponen circulo rojo (badge). El resto: solo timeline.
PRIORIDADES_BADGE = {"CRITICA", "ALTA", "MEDIA"}

# tipo de evento -> slug de PESTAÑA dentro del modulo (granularidad fina de badge). Solo se incluyen
# aqui los tipos cuyo punto de emision es inequivoco (un unico origen real) — un tipo ausente de este
# dict sigue haciendo badge a nivel de MODULO (comportamiento previo, sin cambios) pero no descuenta
# pestaña a pestaña, salvo que su `origen` esté mapeado en `ORIGEN_A_SUBTAB` (ver mas abajo).
TIPO_A_SUBTAB = {
    "PRECIO_ACTUALIZADO": "precio",
    "UBICACION_ASIGNADA": "asignar",
    "NOMINA_GENERADA": "nominas",
    "COBRO_REGISTRADO": "cobros",
    "REPOSICION_GENERADA": "reposicion",
    "CORREO_RECIBIDO": "recibidos",
    # "MERMA_REGISTRADA" NO se mapea aquí a propósito (se probó con "historial" y se revirtió):
    # `gestion_mermas.py` no tiene ninguna pestaña/sección real a la que enganchar un
    # `marcar_visto("mermas.historial", ...)` (usa sidebar+QStackedWidget sin una página de
    # "Historial" dedicada) — mapear un subtab sin nadie que lo marque como visto es justo lo que
    # causó el bug real reportado: `contar()` empezaba a exigir el watermark "mermas.historial", pero
    # solo `menu_principal.py::manejar_apertura` marca "mermas" (bandera de MÓDULO) al abrir la
    # ventana — el badge dejaba de poder ponerse a cero nunca. Sin entrada aquí, MERMA_REGISTRADA usa
    # el watermark de módulo de siempre, que SÍ se marca correctamente al abrir Mermas.
}

# `origen` de evento -> slug de PESTAÑA. Para tipos EMITIDOS DESDE UNA FUNCION COMPARTIDA por varias
# pantallas (p.ej. `KARDEX_MOVIMIENTO`, `VENTA_REGISTRADA`, `PEDIDO_RECIBIDO`, `DOCUMENTO_PUBLICADO`,
# `CLIENTE_CREADO`, `WORKFLOW_INICIADO`, `ASIENTO_CONTABILIZADO`, `FACTURA_GENERADA`) donde el `tipo`
# por si solo NO distingue que pantalla lo origino — cada llamador pasa su propio `origen` string
# (p.ej. `"tpv"` vs `"autocobro"` vs `"comercial"` para VENTA_REGISTRADA) y ese origen SI distingue la
# pestaña. Se consulta DESPUES de `TIPO_A_SUBTAB` (que tiene prioridad si el tipo ya es inequivoco).
ORIGEN_A_SUBTAB = {}


def vid_de_tipo(tipo) -> str | None:
    return TIPO_A_VID.get(str(tipo or "").upper())


def subtab_de_tipo(tipo) -> str | None:
    return TIPO_A_SUBTAB.get(str(tipo or "").upper())


def subtab_de_evento(tipo, origen=None) -> str | None:
    """Resuelve la pestaña de un evento: primero por `tipo` (inequivoco, `TIPO_A_SUBTAB`), y si no
    hay match, por `origen` (`ORIGEN_A_SUBTAB`, para tipos de funcion compartida)."""
    s = subtab_de_tipo(tipo)
    if s:
        return s
    return ORIGEN_A_SUBTAB.get(str(origen or ""))


def hace_badge(prioridad) -> bool:
    return str(prioridad or "").upper() in PRIORIDADES_BADGE
