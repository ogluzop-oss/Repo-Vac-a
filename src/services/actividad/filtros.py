"""
Filtros rapidos del timeline corporativo (Paquete Enterprise 2, SUBFASE 2.3/2.4).

Categorias rapidas (TODOS/VENTAS/COMPRAS/RRHH/...) → conjunto de tipos de evento (reutiliza los
tipos ya publicados por el Event Bus; no duplica logica). Separadores temporales (Hoy/Ayer/...).
"""

from datetime import date, datetime, timedelta

# Categoria rapida → tipos de evento del Event Bus.
CATEGORIAS = {
    "TODOS": None,
    "VENTAS": ("VENTA_REGISTRADA", "FACTURA_GENERADA", "FACTURA_ANULADA", "FACTURA_RECTIFICADA",
               "COBRO_REGISTRADO"),
    "COMPRAS": ("PEDIDO_RECIBIDO", "PROVEEDOR_ACTUALIZADO"),
    "RRHH": ("NOMINA_GENERADA", "CONTRATO_GENERADO"),
    "FACTURACION": ("FACTURA_GENERADA", "FACTURA_ANULADA", "FACTURA_RECTIFICADA"),
    "CRM": ("CLIENTE_CREADO", "CLIENTE_MODIFICADO"),
    "TESORERIA": ("COBRO_REGISTRADO",),
    "KARDEX": ("KARDEX_MOVIMIENTO",),
    "INVENTARIO": ("INVENTARIO_CORREGIDO", "MERMA_REGISTRADA", "REPOSICION_GENERADA",
                   "UBICACION_ASIGNADA"),
    "WORKFLOW": ("WORKFLOW_INICIADO",),
    "BI": ("BI_SNAPSHOT_GENERADO",),
    "SINCRONIZACION": ("SINCRONIZACION_COMPLETADA",),
    "SEGURIDAD": ("USUARIO_CREADO", "USUARIO_BLOQUEADO", "ROL_MODIFICADO"),
    "DOCUMENTOS": ("DOCUMENTO_PUBLICADO",),
    "CATALOGO": ("PRECIO_ACTUALIZADO", "ARTICULO_CREADO", "ARTICULO_MODIFICADO",
                 "ARTICULO_ELIMINADO", "PROMOCION_PUBLICADA", "PROMOCION_FINALIZADA"),
}

CATEGORIAS_ORDEN = ["TODOS", "VENTAS", "COMPRAS", "FACTURACION", "CRM", "TESORERIA", "KARDEX",
                    "INVENTARIO", "RRHH", "WORKFLOW", "BI", "DOCUMENTOS", "SINCRONIZACION",
                    "SEGURIDAD", "CATALOGO"]


def tipos_de_categoria(categoria):
    """Lista de tipos de la categoria (o None para TODOS)."""
    return CATEGORIAS.get(str(categoria or "TODOS").upper())


def separador_temporal(fecha) -> str:
    """Agrupador cronologico: Hoy / Ayer / Esta semana / Este mes / Mas antiguo."""
    if fecha is None:
        return "Más antiguo"
    try:
        d = fecha.date() if isinstance(fecha, datetime) else (
            fecha if isinstance(fecha, date) else datetime.fromisoformat(str(fecha)[:19]).date())
    except Exception:
        return "Más antiguo"
    hoy = date.today()
    if d == hoy:
        return "Hoy"
    if d == hoy - timedelta(days=1):
        return "Ayer"
    if d >= hoy - timedelta(days=7):
        return "Esta semana"
    if d.year == hoy.year and d.month == hoy.month:
        return "Este mes"
    return "Más antiguo"
