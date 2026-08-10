"""
Conector Shopify · AUDITORÍA (Fase WEB-16). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

SHOPIFY_AUTH = "SHOPIFY_AUTH"
SHOPIFY_VALIDATE = "SHOPIFY_VALIDATE"
SHOPIFY_IMPORT = "SHOPIFY_IMPORT"
SHOPIFY_EXPORT = "SHOPIFY_EXPORT"
SHOPIFY_SYNC_START = "SHOPIFY_SYNC_START"
SHOPIFY_SYNC_FINISH = "SHOPIFY_SYNC_FINISH"
SHOPIFY_ERROR = "SHOPIFY_ERROR"

EVENTOS = (SHOPIFY_AUTH, SHOPIFY_VALIDATE, SHOPIFY_IMPORT, SHOPIFY_EXPORT, SHOPIFY_SYNC_START,
           SHOPIFY_SYNC_FINISH, SHOPIFY_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento Shopify en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "shopify",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
