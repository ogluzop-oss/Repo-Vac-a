"""
Adaptador Hostinger · AUDITORÍA (Fase WEB-14). Eventos canónicos del ciclo de vida de la integración
Hostinger, sobre el `log_auditoria` existente (N7; sin motor de eventos nuevo).
"""

import logging

logger = logging.getLogger("marketplace.integraciones_comerciales.hostinger")

HOSTINGER_AUTH = "HOSTINGER_AUTH"
HOSTINGER_CREATE = "HOSTINGER_CREATE"
HOSTINGER_COMPLETE = "HOSTINGER_COMPLETE"
HOSTINGER_CONNECTED = "HOSTINGER_CONNECTED"
HOSTINGER_REGISTERED = "HOSTINGER_REGISTERED"
HOSTINGER_SYNC = "HOSTINGER_SYNC"
HOSTINGER_ERROR = "HOSTINGER_ERROR"

EVENTOS = (HOSTINGER_AUTH, HOSTINGER_CREATE, HOSTINGER_COMPLETE, HOSTINGER_CONNECTED,
           HOSTINGER_REGISTERED, HOSTINGER_SYNC, HOSTINGER_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento Hostinger en la auditoría. Degradable (nunca rompe) y NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "hostinger",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
