"""
Conector WooCommerce · SECRETOS (Fase WEB-15). Consumer Key/Secret vía el `SecretManager` existente. NUNCA se
guardan en claro/JSON/variables globales. `credenciales_ref` = NOMBRE base del secreto.

Almacenamiento en runtime (p. ej. desde la UI): se CIFRA con `secret_manager.cifrar` (Fernet) y se retiene en
memoria por referencia — nunca el valor en claro ni en disco/git. En producción, `obtener_secreto` resuelve
desde el backend real (AWS Secrets Manager / entorno).
"""

_RUNTIME = {}   # ref -> (ck_cifrado, cs_cifrado)  — cifrado Fernet, jamás en claro


def guardar_runtime(ref, consumer_key, consumer_secret) -> None:
    """Guarda CK/CS CIFRADOS en memoria bajo `ref` (reutiliza el cifrado del SecretManager)."""
    from src.services.seguridad import secret_manager as sm
    _RUNTIME[ref or "WOO"] = (sm.cifrar(consumer_key), sm.cifrar(consumer_secret))


def credenciales(ref=None):
    """Devuelve (consumer_key, consumer_secret). Prioriza el runtime cifrado; si no, el SecretManager por
    nombre (entorno/AWS). Devuelve (None, None) si no hay credenciales → adaptador NO disponible (honesto)."""
    ref = ref or "WOO"
    from src.services.seguridad import secret_manager as sm
    if ref in _RUNTIME:
        ckc, csc = _RUNTIME[ref]
        return sm.descifrar(ckc), sm.descifrar(csc)
    ck = sm.obtener_secreto(f"{ref}_CONSUMER_KEY") or sm.obtener_secreto("WOO_CONSUMER_KEY")
    cs = sm.obtener_secreto(f"{ref}_CONSUMER_SECRET") or sm.obtener_secreto("WOO_CONSUMER_SECRET")
    return ck, cs


def _reset_runtime():
    _RUNTIME.clear()
