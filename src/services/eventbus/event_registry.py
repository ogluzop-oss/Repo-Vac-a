"""
Event Registry (Fase III · B1) — catálogo OFICIAL de eventos corporativos.

Define los eventos estándar de Smart Manager AI para que cualquier módulo publique/suscriba con nombres
consistentes. Extensible: `registrar_evento(...)`. No sustituye el bus existente; lo cataloga.
"""

# Catálogo estándar: nombre → (categoría, descripción). Ampliable.
ESTANDAR = {
    # Comunicaciones (CCP)
    "CommunicationCreated": ("comunicacion", "Comunicación creada"),
    "CommunicationSent": ("comunicacion", "Comunicación enviada"),
    "CommunicationDelivered": ("comunicacion", "Comunicación entregada"),
    "CommunicationFailed": ("comunicacion", "Comunicación fallida"),
    "ConsentChanged": ("comunicacion", "Consentimiento RGPD modificado"),
    # Workflow
    "WorkflowStarted": ("workflow", "Workflow iniciado"),
    "WorkflowCompleted": ("workflow", "Workflow completado"),
    # Campañas
    "CampaignStarted": ("campana", "Campaña iniciada"),
    "CampaignFinished": ("campana", "Campaña finalizada"),
    # Notificaciones
    "NotificationCreated": ("notificacion", "Notificación creada"),
    "NotificationRead": ("notificacion", "Notificación leída"),
    # Negocio
    "InvoiceGenerated": ("facturacion", "Factura generada"),
    "InvoicePaid": ("facturacion", "Factura cobrada"),
    "StockUpdated": ("stock", "Stock actualizado"),
    "TransferCompleted": ("logistica", "Traspaso completado"),
    "EmployeeCreated": ("rrhh", "Empleado creado"),
    "ContractSigned": ("rrhh", "Contrato firmado"),
    "PurchaseOrderApproved": ("compras", "Pedido de compra aprobado"),
    # Comercio Digital · Canal Web (tienda online)
    "CanalWebCreating": ("comercio", "Canal web generándose"),
    "CanalWebCreated": ("comercio", "Canal web creado"),
    "CanalWebPublished": ("comercio", "Canal web publicado"),
    "CanalWebUnpublished": ("comercio", "Canal web despublicado"),
    "CanalWebRegenerated": ("comercio", "Canal web regenerado"),
    "CanalWebConfigUpdated": ("comercio", "Configuración del canal web actualizada"),
    "CanalWebSynced": ("comercio", "Canal web sincronizado"),
    # Canal Web · Dominios
    "CanalWebDominioBuscado": ("comercio", "Búsqueda de dominio realizada"),
    "CanalWebDominioComprado": ("comercio", "Dominio comprado"),
    "CanalWebSubdominioCreado": ("comercio", "Subdominio Smart Manager creado"),
    "CanalWebDominioAsignado": ("comercio", "Dominio asignado al canal web"),
    "CanalWebDNSConfigurado": ("comercio", "DNS del canal web configurado"),
    "CanalWebHTTPSConfigurado": ("comercio", "HTTPS del canal web configurado"),
    # Comercio Digital · Recogida en tienda (Click & Collect)
    "PICKUP_RESERVED": ("comercio", "Recogida en tienda reservada"),
    "PICKUP_PREPARED": ("comercio", "Pedido de recogida preparado"),
    "PICKUP_COLLECTED": ("comercio", "Pedido recogido en tienda"),
    "PICKUP_CANCELLED": ("comercio", "Reserva de recogida cancelada"),
    "PICKUP_EXPIRED": ("comercio", "Reserva de recogida expirada"),
    "PICKUP_REFUNDED": ("comercio", "Reembolso de recogida realizado"),
    # Plataforma
    "AuditCreated": ("auditoria", "Registro de auditoría creado"),
    "PluginInstalled": ("plugin", "Plugin instalado"),
    "PluginRemoved": ("plugin", "Plugin eliminado"),
}

_EXTRA: dict = {}


def registrar_evento(nombre, *, categoria="general", descripcion=None):
    """Registra un evento nuevo en el catálogo (extensible por módulos/plugins)."""
    _EXTRA[nombre] = (categoria, descripcion or nombre)
    return nombre


def catalogo() -> dict:
    d = dict(ESTANDAR); d.update(_EXTRA); return d


def es_estandar(nombre) -> bool:
    return nombre in ESTANDAR or nombre in _EXTRA


def por_categoria(categoria) -> list:
    return [n for n, (c, _) in catalogo().items() if c == categoria]
