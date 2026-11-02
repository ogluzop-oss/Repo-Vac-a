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


def credenciales(ref=None, id_empresa=None):
    """Devuelve (consumer_key, consumer_secret). Prioriza: la `ref` explícita; si no, la ref POR EMPRESA
    (`WOO_<id_empresa>` — la que usa el asistente de alta al guardar CK/CS en runtime); si no, la ref
    global "WOO" (entorno/AWS). Devuelve (None, None) si no hay credenciales → adaptador NO disponible
    (honesto). El `id_empresa` es imprescindible para que el adaptador encuentre las credenciales que el
    asistente de Integraciones Comerciales guardó bajo la referencia por-empresa (multiempresa estricto)."""
    from src.services.seguridad import secret_manager as sm
    candidatos = []
    for r in (ref, f"WOO_{id_empresa}" if id_empresa is not None else None, "WOO"):
        if r and r not in candidatos:
            candidatos.append(r)
    for r in candidatos:
        if r in _RUNTIME:
            ckc, csc = _RUNTIME[r]
            return sm.descifrar(ckc), sm.descifrar(csc)
    for r in candidatos:
        ck = sm.obtener_secreto(f"{r}_CONSUMER_KEY")
        cs = sm.obtener_secreto(f"{r}_CONSUMER_SECRET")
        if ck or cs:
            return ck, cs
    return None, None


def _reset_runtime():
    _RUNTIME.clear()
