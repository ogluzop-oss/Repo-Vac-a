"""
Channel Policy — política de selección de canal de la CCP.

Hoy la política devuelve siempre 'email' (único canal operativo). Queda preparada para decidir por
preferencias del destinatario, tipo documental o reglas corporativas SIN tocar el resto: el día que un
cliente prefiera WhatsApp, solo cambia esta política. Si el canal preferido no está operativo, degrada
a Email.
"""

import logging

from src.services.ccp import canales as _canales
from src.services.ccp.modelo import CANAL_EMAIL

logger = logging.getLogger("ccp.politica_canal")


def seleccionar_canal(comunicacion, destinatario=None) -> str:
    """Devuelve la clave del canal a usar. Prioridad: canal forzado en la comunicación → canal
    preferido del destinatario (si está operativo) → Email (por defecto)."""
    # 1) Canal forzado explícitamente.
    if getattr(comunicacion, "canal", None):
        return comunicacion.canal
    # 2) Preferencia del destinatario (campo preparado en el perfil), solo si el canal está operativo.
    pref = getattr(destinatario, "canal_preferido", None)
    if pref:
        c = _canales.canal(pref)
        if c is not None and c.disponible():
            return pref
        logger.debug("canal preferido '%s' no operativo; se degrada a email", pref)
    # 3) Por defecto: Email.
    return CANAL_EMAIL
