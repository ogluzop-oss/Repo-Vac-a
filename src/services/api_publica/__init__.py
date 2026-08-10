"""
API Pública para terceros (Fase V · Bloque 3) — fachada.

Permite que empresas externas desarrollen integraciones oficiales: Portal Developer, SDK (Python/JS/
TS/C#/Java/PHP), OAuth2 (client-credentials + scopes), sandbox, rate limiting, OpenAPI/Swagger y
versionado. REUTILIZA la REST API, la seguridad (JWT/API Keys/rate limit) y el OpenAPI existentes.
Multiempresa (cada app pertenece a una empresa).

    from src.services import api_publica
    app = api_publica.registrar_app("Integración X", id_empresa=emp, scopes=["read:orders"])
    tok = api_publica.emitir_token(app["client_id"], app["client_secret"])
"""

from src.services.api_publica.developer import (  # noqa: F401
    SCOPES_DISPONIBLES, registrar_app, obtener_app, verificar_credenciales, listar_apps, revocar_app,
)
from src.services.api_publica.oauth import emitir_token, verificar_scope  # noqa: F401
from src.services.api_publica import sdks, openapi_publica  # noqa: F401

__all__ = ["SCOPES_DISPONIBLES", "registrar_app", "obtener_app", "verificar_credenciales",
           "listar_apps", "revocar_app", "emitir_token", "verificar_scope", "sdks",
           "openapi_publica"]
