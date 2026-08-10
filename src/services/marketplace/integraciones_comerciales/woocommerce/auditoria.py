"""
Conector WooCommerce · AUDITORÍA (Fase WEB-15). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

WOO_AUTH = "WOO_AUTH"
WOO_VALIDATE = "WOO_VALIDATE"
WOO_IMPORT = "WOO_IMPORT"
WOO_EXPORT = "WOO_EXPORT"
WOO_SYNC_START = "WOO_SYNC_START"
WOO_SYNC_FINISH = "WOO_SYNC_FINISH"
WOO_ERROR = "WOO_ERROR"

EVENTOS = (WOO_AUTH, WOO_VALIDATE, WOO_IMPORT, WOO_EXPORT, WOO_SYNC_START, WOO_SYNC_FINISH, WOO_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento WooCommerce en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "woocommerce",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
