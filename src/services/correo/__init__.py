"""Servicio de correo corporativo (envío de documentos + OAuth 2.0)."""

from src.services.correo.servicio import (
    enviar_documento,
    estado_oauth,
    oauth_google_configurado,
    iniciar_oauth_google,
)

__all__ = [
    "enviar_documento",
    "estado_oauth",
    "oauth_google_configurado",
    "iniciar_oauth_google",
]
