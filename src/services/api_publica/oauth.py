"""
API Pública · OAuth2 (Fase V · Bloque 3). Flujo client-credentials para terceros: valida la app de
desarrollador y emite un JWT con scopes REUTILIZANDO `src.seguridad.tokens` (no crea un segundo
sistema de tokens). El tenant y los scopes viajan en el token; el rate limit y la seguridad los
aplica la REST API existente (`src.api.security`).
"""

from __future__ import annotations

from src.services.api_publica import developer


def emitir_token(client_id, client_secret, *, scopes=()) -> dict | None:
    """Client-credentials: devuelve un access token acotado a los scopes concedidos a la app."""
    app = developer.verificar_credenciales(client_id, client_secret)
    if not app:
        return None
    concedidos = set((app.get("scopes") or "").split(",")) if app.get("scopes") else set()
    pedidos = set(scopes) or concedidos
    efectivos = sorted(pedidos & concedidos) if concedidos else []
    from src.seguridad import tokens
    usuario = {"id": client_id, "id_empresa": app.get("id_empresa"), "perfil": "API",
               "nombre": app.get("nombre"), "scopes": efectivos}
    access = tokens.emitir_access(usuario)
    return {"access_token": access, "token_type": "Bearer", "scopes": efectivos,
            "sandbox": bool(app.get("sandbox"))}


def verificar_scope(token, scope) -> bool:
    """Verifica un scope. El JWT oficial no transporta scopes personalizados, así que se resuelven
    desde la app de desarrollador identificada por el `sub` (= client_id) del token."""
    from src.seguridad import tokens
    claims = tokens.verificar(token, "access")
    if not claims:
        return False
    if str(claims.get("rol") or claims.get("perfil")).upper() == "ADMINISTRADOR":
        return True
    app = developer.obtener_app(claims.get("sub"))
    if not app or app.get("estado") != "activa":
        return False
    concedidos = set((app.get("scopes") or "").split(",")) if app.get("scopes") else set()
    return scope in concedidos


__all__ = ["emitir_token", "verificar_scope"]
