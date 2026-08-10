"""
Conector Miravia · AUDITORÍA (Fase WEB-22). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

MIRAVIA_AUTH = "MIRAVIA_AUTH"
MIRAVIA_VALIDATE = "MIRAVIA_VALIDATE"
MIRAVIA_IMPORT = "MIRAVIA_IMPORT"
MIRAVIA_EXPORT = "MIRAVIA_EXPORT"
MIRAVIA_SYNC_START = "MIRAVIA_SYNC_START"
MIRAVIA_SYNC_FINISH = "MIRAVIA_SYNC_FINISH"
MIRAVIA_ERROR = "MIRAVIA_ERROR"

EVENTOS = (MIRAVIA_AUTH, MIRAVIA_VALIDATE, MIRAVIA_IMPORT, MIRAVIA_EXPORT, MIRAVIA_SYNC_START,
           MIRAVIA_SYNC_FINISH, MIRAVIA_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento Miravia en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "miravia",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
