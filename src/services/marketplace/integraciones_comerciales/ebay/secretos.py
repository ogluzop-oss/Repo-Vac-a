"""
Conector eBay · SECRETOS (Fase WEB-21). Access Token (OAuth2 de usuario) vía el `SecretManager` existente.
NUNCA en claro/JSON/variables globales. Runtime: se CIFRA (Fernet) y se retiene por referencia; producción →
entorno/AWS. `credenciales_ref` = NOMBRE base del secreto. El endpoint base NO es secreto.
"""

_RUNTIME = {}   # ref -> access_token_cifrado


def guardar_runtime(ref, access_token) -> None:
    """Guarda el Access Token CIFRADO en memoria bajo `ref` (reutiliza el cifrado del SecretManager)."""
    from src.services.seguridad import secret_manager as sm
    _RUNTIME[ref or "EBAY"] = sm.cifrar(access_token)


def access_token(ref=None):
    """Devuelve el Access Token. Prioriza el runtime cifrado; si no, el SecretManager por nombre (entorno/
    AWS). None si no hay credenciales → adaptador NO disponible (honesto)."""
    ref = ref or "EBAY"
    from src.services.seguridad import secret_manager as sm
    if ref in _RUNTIME:
        return sm.descifrar(_RUNTIME[ref])
    return sm.obtener_secreto(f"{ref}_ACCESS_TOKEN") or sm.obtener_secreto("EBAY_ACCESS_TOKEN")


def _reset_runtime():
    _RUNTIME.clear()
