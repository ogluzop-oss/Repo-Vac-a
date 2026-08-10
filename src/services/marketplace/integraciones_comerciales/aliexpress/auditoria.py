"""
Conector AliExpress · AUDITORÍA (Fase WEB-23). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

ALIEXPRESS_AUTH = "ALIEXPRESS_AUTH"
ALIEXPRESS_VALIDATE = "ALIEXPRESS_VALIDATE"
ALIEXPRESS_IMPORT = "ALIEXPRESS_IMPORT"
ALIEXPRESS_EXPORT = "ALIEXPRESS_EXPORT"
ALIEXPRESS_SYNC_START = "ALIEXPRESS_SYNC_START"
ALIEXPRESS_SYNC_FINISH = "ALIEXPRESS_SYNC_FINISH"
ALIEXPRESS_ERROR = "ALIEXPRESS_ERROR"

EVENTOS = (ALIEXPRESS_AUTH, ALIEXPRESS_VALIDATE, ALIEXPRESS_IMPORT, ALIEXPRESS_EXPORT,
           ALIEXPRESS_SYNC_START, ALIEXPRESS_SYNC_FINISH, ALIEXPRESS_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento AliExpress en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "aliexpress",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
