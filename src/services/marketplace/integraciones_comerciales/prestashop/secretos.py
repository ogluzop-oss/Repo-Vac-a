"""
Conector PrestaShop · SECRETOS (Fase WEB-17). API Key del Webservice vía el `SecretManager` existente. NUNCA
en claro/JSON/variables globales. Runtime: se CIFRA (Fernet) y se retiene por referencia; producción →
entorno/AWS. `credenciales_ref` = NOMBRE base del secreto. La Shop URL NO es secreto (va en la integración).
"""

_RUNTIME = {}   # ref -> api_key_cifrada


def guardar_runtime(ref, api_key) -> None:
    """Guarda la API Key CIFRADA en memoria bajo `ref` (reutiliza el cifrado del SecretManager)."""
    from src.services.seguridad import secret_manager as sm
    _RUNTIME[ref or "PRESTASHOP"] = sm.cifrar(api_key)


def api_key(ref=None):
    """Devuelve la API Key. Prioriza el runtime cifrado; si no, el SecretManager por nombre (entorno/AWS).
    None si no hay credenciales → adaptador NO disponible (honesto)."""
    ref = ref or "PRESTASHOP"
    from src.services.seguridad import secret_manager as sm
    if ref in _RUNTIME:
        return sm.descifrar(_RUNTIME[ref])
    return sm.obtener_secreto(f"{ref}_API_KEY") or sm.obtener_secreto("PRESTASHOP_API_KEY")


def _reset_runtime():
    _RUNTIME.clear()
