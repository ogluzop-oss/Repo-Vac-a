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


def vid_de_tipo(tipo) -> str | None:
    return TIPO_A_VID.get(str(tipo or "").upper())


def hace_badge(prioridad) -> bool:
    return str(prioridad or "").upper() in PRIORIDADES_BADGE
