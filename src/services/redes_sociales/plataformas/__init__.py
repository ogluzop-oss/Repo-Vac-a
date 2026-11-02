"""
Clientes HTTP reales por plataforma social (Meta Graph API para Instagram+Facebook, TikTok, YouTube
Data API, X API v2). Todos comparten `services.redes_sociales.transporte` y degradan honestamente
(`{"ok": False, "estado": "no_configurado"|"error", ...}`, nunca datos simulados) cuando la cuenta
no está conectada o la plataforma no expone la capacidad pedida para apps de terceros.
"""

from src.services.redes_sociales.plataformas import meta as _meta
from src.services.redes_sociales.plataformas import tiktok as _tiktok
from src.services.redes_sociales.plataformas import x as _x
from src.services.redes_sociales.plataformas import youtube as _youtube

CLIENTES = {
    "instagram": _meta,
    "facebook": _meta,
    "tiktok": _tiktok,
    "youtube": _youtube,
    "x": _x,
}


def cliente_para(plataforma):
    """Módulo cliente real para una plataforma, o None si no está soportada."""
    return CLIENTES.get(plataforma)
