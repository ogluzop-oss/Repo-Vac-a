"""
Conector Shopify · SECRETOS (Fase WEB-16). Access Token vía el `SecretManager` existente. NUNCA en claro/JSON/
variables globales. Runtime: se CIFRA (Fernet) y se retiene por referencia; producción → entorno/AWS.
`credenciales_ref` = NOMBRE base del secreto. La Shop URL NO es secreto (se guarda en la integración).
"""

_RUNTIME = {}   # ref -> access_token_cifrado


def guardar_runtime(ref, access_token) -> None:
    """Guarda el Access Token CIFRADO en memoria bajo `ref` (reutiliza el cifrado del SecretManager)."""
    from src.services.seguridad import secret_manager as sm
    _RUNTIME[ref or "SHOPIFY"] = sm.cifrar(access_token)


def access_token(ref=None, id_empresa=None):
    """Devuelve el Access Token. Prioriza: la `ref` explícita; si no, la ref POR EMPRESA
    (`SHOPIFY_<id_empresa>` — la que usa el asistente de alta al guardar el token en runtime); si no, la
    ref global "SHOPIFY" (entorno/AWS). None si no hay credenciales → adaptador NO disponible (honesto).
    El `id_empresa` es imprescindible para que el adaptador encuentre las credenciales que el asistente de
    Integraciones Comerciales guardó bajo la referencia por-empresa (multiempresa estricto)."""
    from src.services.seguridad import secret_manager as sm
    candidatos = []
    for r in (ref, f"SHOPIFY_{id_empresa}" if id_empresa is not None else None, "SHOPIFY"):
        if r and r not in candidatos:
            candidatos.append(r)
    for r in candidatos:
        if r in _RUNTIME:
            return sm.descifrar(_RUNTIME[r])
    for r in candidatos:
        tok = sm.obtener_secreto(f"{r}_ACCESS_TOKEN")
        if tok:
            return tok
    return None


def _reset_runtime():
    _RUNTIME.clear()
