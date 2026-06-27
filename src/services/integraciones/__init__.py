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
}


def disponibles() -> dict:
    return dict(CONECTORES)


def enviar(conector, mensaje, *, url=None, config=None, transport=None):
    """Punto único de salida. Para conectores http_webhook envía un POST con el mensaje;
    para los de credenciales devuelve estado 'no_configurado' si falta config (sin romper)."""
    cat = CONECTORES.get(conector)
    if cat is None:
        return {"ok": False, "estado": "desconocido", "conector": conector}
    if cat == "http_webhook":
        from src.services.integraciones.http_webhook import enviar_webhook
        return enviar_webhook(url, mensaje, transport=transport)
    # Conector basado en credenciales/SDK: requiere configuración explícita.
    if not config:
        return {"ok": False, "estado": "no_configurado", "conector": conector}
    return {"ok": False, "estado": "no_implementado", "conector": conector}
