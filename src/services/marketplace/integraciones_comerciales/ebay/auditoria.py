"""
Conector eBay · AUDITORÍA (Fase WEB-21). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

EBAY_AUTH = "EBAY_AUTH"
EBAY_VALIDATE = "EBAY_VALIDATE"
EBAY_IMPORT = "EBAY_IMPORT"
EBAY_EXPORT = "EBAY_EXPORT"
EBAY_SYNC_START = "EBAY_SYNC_START"
EBAY_SYNC_FINISH = "EBAY_SYNC_FINISH"
EBAY_ERROR = "EBAY_ERROR"

EVENTOS = (EBAY_AUTH, EBAY_VALIDATE, EBAY_IMPORT, EBAY_EXPORT, EBAY_SYNC_START, EBAY_SYNC_FINISH,
           EBAY_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento eBay en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "ebay",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
