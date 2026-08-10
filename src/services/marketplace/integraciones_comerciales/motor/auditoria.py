"""
Motor · AUDITORÍA (Fase WEB-13). Eventos canónicos del ciclo de vida de una integración. Reutiliza el
`log_auditoria` existente (N7) — NO crea un motor de eventos nuevo. Sin eventos reales de sincronización.
"""

import logging

logger = logging.getLogger("marketplace.integraciones_comerciales.motor")

# Eventos canónicos (nombres estables).
INTEGRATION_CREATED = "INTEGRATION_CREATED"
INTEGRATION_VALIDATED = "INTEGRATION_VALIDATED"
INTEGRATION_SYNC_STARTED = "INTEGRATION_SYNC_STARTED"
INTEGRATION_SYNC_FINISHED = "INTEGRATION_SYNC_FINISHED"
INTEGRATION_DISABLED = "INTEGRATION_DISABLED"
INTEGRATION_ENABLED = "INTEGRATION_ENABLED"

EVENTOS = (INTEGRATION_CREATED, INTEGRATION_VALIDATED, INTEGRATION_SYNC_STARTED,
           INTEGRATION_SYNC_FINISHED, INTEGRATION_DISABLED, INTEGRATION_ENABLED)


def registrar_evento(evento: str, *, id_empresa=None, plataforma=None, usuario=None, detalle=None) -> bool:
    """Registra un evento de integración en la auditoría existente. Degradable (nunca rompe)."""
    if evento not in EVENTOS:
        logger.debug("evento de integración no canónico: %s", evento)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "integraciones_comerciales",
                      f"emp={id_empresa} plataforma={plataforma} por={usuario} {detalle or ''}".strip())
        return True
    except Exception:
        return False
