"""
GraphQL Enterprise · Context (Fase IV · Bloque 1). Construye el contexto autenticado de una
operación GraphQL REUTILIZANDO la seguridad de la REST API (JWT / API Key). El tenant (`id_empresa`)
sale SIEMPRE del token/clave, nunca de los argumentos — aislamiento multiempresa estricto.
"""

from __future__ import annotations


def desde_request():
    """Contexto a partir de la request Flask actual (JWT/API Key), vía la seguridad REST."""
    try:
        from src.api.security import contexto_de_request
        ctx = contexto_de_request()
        if ctx:
            return {"id_empresa": ctx.get("id_empresa"), "usuario": ctx.get("usuario") or {},
                    "auth": ctx.get("auth"), "scopes": tuple(ctx.get("scopes") or ())}
    except Exception:
        pass
    return None


def desde_dict(d):
    """Contexto explícito (integraciones internas / tests). Normaliza la forma."""
    d = d or {}
    usuario = d.get("usuario") or {}
    return {"id_empresa": d.get("id_empresa") or usuario.get("id_empresa"),
            "usuario": usuario, "auth": d.get("auth", "interno"),
            "scopes": tuple(d.get("scopes") or ())}


def id_empresa(ctx):
    ctx = ctx or {}
    return ctx.get("id_empresa") or (ctx.get("usuario") or {}).get("id_empresa")


def usuario(ctx):
    return (ctx or {}).get("usuario") or {}


__all__ = ["desde_request", "desde_dict", "id_empresa", "usuario"]
