"""
Conector Amazon · AUDITORÍA (Fase WEB-20). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

AMAZON_AUTH = "AMAZON_AUTH"
AMAZON_VALIDATE = "AMAZON_VALIDATE"
AMAZON_IMPORT = "AMAZON_IMPORT"
AMAZON_EXPORT = "AMAZON_EXPORT"
AMAZON_SYNC_START = "AMAZON_SYNC_START"
AMAZON_SYNC_FINISH = "AMAZON_SYNC_FINISH"
AMAZON_ERROR = "AMAZON_ERROR"

EVENTOS = (AMAZON_AUTH, AMAZON_VALIDATE, AMAZON_IMPORT, AMAZON_EXPORT, AMAZON_SYNC_START,
           AMAZON_SYNC_FINISH, AMAZON_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento Amazon en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "amazon",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
