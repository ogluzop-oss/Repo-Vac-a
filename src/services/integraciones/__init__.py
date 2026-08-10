"""
Capa de conectores externos (FASE COM-10).

Framework uniforme de conectores: cada conector implementa `enviar(accion, **kw)`. Registro
central + resolución por código. Los conectores que solo requieren una URL de webhook entrante
(Slack/Telegram/Teams) están implementados sobre HTTP; los que requieren SDK/credenciales
(M365 Graph, Google Calendar, DocuSign, Dropbox/OneDrive/SharePoint, Twilio, WhatsApp) se
declaran y validan su configuración, devolviendo un resultado controlado si no están configurados.
No introduce dependencias nuevas obligatorias (requests es opcional).
"""

import logging

logger = logging.getLogger("integraciones")

# Conectores declarados (código → categoría). Los "http_webhook" están operativos.
CONECTORES = {
    "slack": "http_webhook", "telegram": "http_webhook", "teams": "http_webhook",
    "msgraph": "credenciales", "outlook": "credenciales", "exchange": "credenciales",
    "google_calendar": "credenciales", "google_workspace": "credenciales",
    "whatsapp": "credenciales", "twilio": "credenciales", "zoom": "credenciales",
    "dropbox": "credenciales", "onedrive": "credenciales", "sharepoint": "credenciales",
    "docusign": "credenciales", "adobe_sign": "credenciales",
    # Conectores Enterprise oficiales (Etapa E · Fase E2) — ERP/CRM/eCommerce sobre el Adapter Pattern
    # (RestChannelAdapter) + conexiones cifradas (Secret Manager). Ver `integraciones.enterprise`.
    "sap": "enterprise", "salesforce": "enterprise", "woocommerce": "enterprise",
    "prestashop": "enterprise", "magento": "enterprise", "business_central": "enterprise",
    "dynamics365": "enterprise",
}


def disponibles() -> dict:
    return dict(CONECTORES)


def enviar(conector, mensaje, *, url=None, config=None, transport=None, para=None, asunto=None):
    """Punto único de salida. Webhooks → POST; conectores de correo con credenciales (msgraph/outlook/
    exchange) → envío REAL vía Graph cuando hay config (Bloque 2); resto → degradación controlada."""
    cat = CONECTORES.get(conector)
    if cat is None:
        return {"ok": False, "estado": "desconocido", "conector": conector}
    if cat == "http_webhook":
        from src.services.integraciones.http_webhook import enviar_webhook
        return enviar_webhook(url, mensaje, transport=transport)
    if cat == "enterprise":
        # Conectores Enterprise (E2): delegan en la fachada que reutiliza el Adapter Pattern +
        # conexiones cifradas. `config` puede aportar id_empresa/nombre (multiempresa); nunca credenciales.
        from src.services.integraciones import enterprise
        cfg = config or {}
        return enterprise.enviar(conector, mensaje, id_empresa=cfg.get("id_empresa"),
                                 nombre=cfg.get("nombre", "default"), transporte=transport)
    if not config:
        return {"ok": False, "estado": "no_configurado", "conector": conector}
    # Conectores de correo Microsoft (envío real vía Graph; degrada limpio sin token).
    if conector in ("msgraph", "outlook", "exchange") and para:
        from src.services.integraciones import conectores
        return conectores.outlook_enviar(config=config, para=para,
                                         asunto=asunto or "(sin asunto)", cuerpo=mensaje)
    return {"ok": False, "estado": "no_implementado", "conector": conector}


# ── Puntos de entrada de alto nivel (Bloque 2) — enrutan al conector real, degradando ──
def calendario(accion, *, proveedor="google", cuenta=None, config=None, evento=None, evento_id=None):
    """Calendario multi-proveedor: leer/crear/editar/cancelar eventos. proveedor ∈ google|outlook."""
    from src.services.integraciones import conectores
    if proveedor == "google":
        return conectores.google_calendar(accion, id_correo=cuenta, evento=evento, evento_id=evento_id)
    if proveedor in ("outlook", "msgraph", "exchange"):
        return conectores.outlook_calendar(accion, config=config, evento=evento, evento_id=evento_id)
    return {"ok": False, "estado": "proveedor_desconocido", "proveedor": proveedor}


def firma_enviar(*, config, sobre):
    """Firma electrónica (DocuSign): envía un sobre. Degrada sin configuración."""
    from src.services.integraciones import conectores
    return conectores.docusign_enviar_sobre(config=config, sobre=sobre)


def firma_estado(*, config, envelope_id):
    """Seguimiento/estado de una firma electrónica (DocuSign)."""
    from src.services.integraciones import conectores
    return conectores.docusign_estado(config=config, envelope_id=envelope_id)


def documento_subir(*, proveedor="google", cuenta=None, ruta=None, nombre=None):
    """Archiva/adjunta un documento (factura/contrato/albarán…) en el almacenamiento del proveedor."""
    from src.services.integraciones import conectores
    if proveedor == "google":
        return conectores.google_drive_subir(id_correo=cuenta, ruta=ruta, nombre=nombre)
    return {"ok": False, "estado": "proveedor_desconocido", "proveedor": proveedor}
