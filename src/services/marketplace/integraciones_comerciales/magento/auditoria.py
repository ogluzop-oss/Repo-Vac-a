"""
Conector Magento · AUDITORÍA (Fase WEB-18). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

MAGENTO_AUTH = "MAGENTO_AUTH"
MAGENTO_VALIDATE = "MAGENTO_VALIDATE"
MAGENTO_IMPORT = "MAGENTO_IMPORT"
MAGENTO_EXPORT = "MAGENTO_EXPORT"
MAGENTO_SYNC_START = "MAGENTO_SYNC_START"
MAGENTO_SYNC_FINISH = "MAGENTO_SYNC_FINISH"
MAGENTO_ERROR = "MAGENTO_ERROR"

EVENTOS = (MAGENTO_AUTH, MAGENTO_VALIDATE, MAGENTO_IMPORT, MAGENTO_EXPORT, MAGENTO_SYNC_START,
           MAGENTO_SYNC_FINISH, MAGENTO_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento Magento en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "magento",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
