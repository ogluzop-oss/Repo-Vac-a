"""
Conector Meta Shop (Instagram Shopping + Facebook Shop) · SECRETOS. Mismo patrón que
`tiktok_shop/secretos.py`: el token de acceso con permiso `catalog_management` vía el
`SecretManager` existente, cifrado (Fernet), nunca en claro. `credenciales_ref` = nombre base del
secreto (permite varias cuentas/credenciales independientes por empresa si hiciera falta).
"""

_RUNTIME = {}   # ref -> (access_token_cifrado, catalog_id)


def guardar_runtime(ref, access_token, catalog_id=None) -> None:
    from src.services.seguridad import secret_manager as sm
    _RUNTIME[ref or "META_SHOP"] = (sm.cifrar(access_token), catalog_id)


def access_token(ref=None):
    ref = ref or "META_SHOP"
    from src.services.seguridad import secret_manager as sm
    if ref in _RUNTIME:
        return sm.descifrar(_RUNTIME[ref][0])
    return sm.obtener_secreto(f"{ref}_ACCESS_TOKEN") or sm.obtener_secreto("META_SHOP_ACCESS_TOKEN")


def catalog_id(ref=None):
    ref = ref or "META_SHOP"
    from src.services.seguridad import secret_manager as sm
    if ref in _RUNTIME and _RUNTIME[ref][1]:
        return _RUNTIME[ref][1]
    return sm.obtener_secreto(f"{ref}_CATALOG_ID") or sm.obtener_secreto("META_SHOP_CATALOG_ID")


def _reset_runtime():
    _RUNTIME.clear()
