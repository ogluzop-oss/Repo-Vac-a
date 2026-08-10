"""
Conector Web tradicional · SECRETOS (Modo B, REST). Token de acceso a la API de la PROPIA web del cliente,
vía el `SecretManager` existente. NUNCA en claro/JSON/variables globales. `ref` = nombre base del secreto.

Runtime (p. ej. desde la UI): se CIFRA con `secret_manager.cifrar` (Fernet) y se retiene en memoria por
referencia — nunca el valor en claro ni en disco/git. En producción, `obtener_secreto` resuelve del backend
real (AWS Secrets Manager / entorno).
"""

_RUNTIME = {}   # ref -> token_cifrado (Fernet, jamás en claro)


def guardar_runtime(ref, token) -> None:
    """Guarda el token CIFRADO en memoria bajo `ref` (reutiliza el cifrado del SecretManager)."""
    from src.services.seguridad import secret_manager as sm
    _RUNTIME[ref or "WEB_REST"] = sm.cifrar(token)


def token(ref=None):
    """Devuelve el token de acceso. Prioriza el runtime cifrado; si no, el SecretManager por nombre
    (entorno/AWS). Devuelve None si no hay token → adaptador NO disponible (honesto, sin red)."""
    ref = ref or "WEB_REST"
    from src.services.seguridad import secret_manager as sm
    if ref in _RUNTIME:
        return sm.descifrar(_RUNTIME[ref])
    return sm.obtener_secreto(f"{ref}_TOKEN") or sm.obtener_secreto("WEB_REST_TOKEN")


def _reset_runtime():
    _RUNTIME.clear()
