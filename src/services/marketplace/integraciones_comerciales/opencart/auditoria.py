"""
Conector OpenCart · AUDITORÍA (Fase WEB-19). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

OPENCART_AUTH = "OPENCART_AUTH"
OPENCART_VALIDATE = "OPENCART_VALIDATE"
OPENCART_IMPORT = "OPENCART_IMPORT"
OPENCART_EXPORT = "OPENCART_EXPORT"
OPENCART_SYNC_START = "OPENCART_SYNC_START"
OPENCART_SYNC_FINISH = "OPENCART_SYNC_FINISH"
OPENCART_ERROR = "OPENCART_ERROR"

EVENTOS = (OPENCART_AUTH, OPENCART_VALIDATE, OPENCART_IMPORT, OPENCART_EXPORT, OPENCART_SYNC_START,
           OPENCART_SYNC_FINISH, OPENCART_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento OpenCart en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "opencart",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
