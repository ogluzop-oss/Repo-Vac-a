"""
GraphQL Enterprise Layer (Fase IV · Bloque 1).

Capa de CONSULTA sobre los servicios existentes — NO una segunda API. Regla inquebrantable:

    GraphQL → Servicios → Dominio → BD     (NUNCA GraphQL → SQL)

Reutiliza la seguridad de la REST API (JWT/API Keys/RBAC/tenant/rate limit) y el Corporate Event Bus
(subscriptions preparadas). Degradable: hoy ejecutor propio ligero; preparado para federar y para
alimentar una librería GraphQL real cuando se instale.

    from src.api.graphql import schema
    schema.ejecutar("communications", {"limite": 20}, contexto={"id_empresa": emp, "usuario": {...}})
    schema.sdl()          # SDL del esquema
    schema.esquema()      # descriptor (tipos + operaciones + servicio de cada una)
"""

from src.api.graphql import context, middlewares, registry, schema  # noqa: F401
from src.api.graphql.descriptor import CONSULTAS, TIPOS, esquema_previsto  # noqa: F401
from src.api.graphql.schema import ejecutar, esquema, sdl  # noqa: F401

__all__ = ["schema", "registry", "context", "middlewares", "ejecutar", "esquema", "sdl",
           "esquema_previsto", "TIPOS", "CONSULTAS"]
