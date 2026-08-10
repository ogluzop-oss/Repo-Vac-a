"""
Conector PrestaShop · AUDITORÍA (Fase WEB-17). Eventos canónicos sobre `log_auditoria` existente (N7).
"""

PRESTA_AUTH = "PRESTA_AUTH"
PRESTA_VALIDATE = "PRESTA_VALIDATE"
PRESTA_IMPORT = "PRESTA_IMPORT"
PRESTA_EXPORT = "PRESTA_EXPORT"
PRESTA_SYNC_START = "PRESTA_SYNC_START"
PRESTA_SYNC_FINISH = "PRESTA_SYNC_FINISH"
PRESTA_ERROR = "PRESTA_ERROR"

EVENTOS = (PRESTA_AUTH, PRESTA_VALIDATE, PRESTA_IMPORT, PRESTA_EXPORT, PRESTA_SYNC_START,
           PRESTA_SYNC_FINISH, PRESTA_ERROR)


def registrar(evento: str, *, id_empresa=None, usuario=None, detalle=None) -> bool:
    """Registra un evento PrestaShop en la auditoría. Degradable; NUNCA vuelca secretos."""
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("marketplace", evento, "prestashop",
                      f"emp={id_empresa} por={usuario} {detalle if detalle is not None else ''}".strip())
        return True
    except Exception:
        return False
