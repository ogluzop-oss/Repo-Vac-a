"""
Conector Meta Shop · AUDITORÍA. Eventos canónicos sobre `log_auditoria` existente (N7), mismo
patrón que `tiktok_shop/auditoria.py`.
"""

META_SHOP_AUTH = "META_SHOP_AUTH"
META_SHOP_VALIDATE = "META_SHOP_VALIDATE"
META_SHOP_IMPORT = "META_SHOP_IMPORT"
META_SHOP_EXPORT = "META_SHOP_EXPORT"
META_SHOP_SYNC_START = "META_SHOP_SYNC_START"
META_SHOP_SYNC_FINISH = "META_SHOP_SYNC_FINISH"
META_SHOP_ERROR = "META_SHOP_ERROR"

EVENTOS = (META_SHOP_AUTH, META_SHOP_VALIDATE, META_SHOP_IMPORT, META_SHOP_EXPORT,
          META_SHOP_SYNC_START, META_SHOP_SYNC_FINISH, META_SHOP_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento Meta Shop en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "meta_shop",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
