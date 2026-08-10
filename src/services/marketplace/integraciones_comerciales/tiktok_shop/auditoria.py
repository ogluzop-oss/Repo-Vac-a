"""
Conector TikTok Shop · AUDITORÍA (Fase WEB-24). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

TIKTOK_AUTH = "TIKTOK_AUTH"
TIKTOK_VALIDATE = "TIKTOK_VALIDATE"
TIKTOK_IMPORT = "TIKTOK_IMPORT"
TIKTOK_EXPORT = "TIKTOK_EXPORT"
TIKTOK_SYNC_START = "TIKTOK_SYNC_START"
TIKTOK_SYNC_FINISH = "TIKTOK_SYNC_FINISH"
TIKTOK_ERROR = "TIKTOK_ERROR"

EVENTOS = (TIKTOK_AUTH, TIKTOK_VALIDATE, TIKTOK_IMPORT, TIKTOK_EXPORT, TIKTOK_SYNC_START,
           TIKTOK_SYNC_FINISH, TIKTOK_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento TikTok Shop en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "tiktok_shop",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
