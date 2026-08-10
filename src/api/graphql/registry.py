"""
GraphQL Enterprise · Registry (Fase IV · Bloque 1). Registro de tipos, queries, mutations y
subscriptions. Cada query/mutation declara su `servicio` de destino (GraphQL→Servicios→Dominio→BD)
y su resolver, que SIEMPRE delega en un servicio existente (nunca SQL directa). Es la fuente única
para construir el esquema (`schema.py`) y ejecutar operaciones.
"""

from __future__ import annotations

_TIPOS: dict = {}          # nombre -> [campos]
_QUERIES: dict = {}        # nombre -> meta
_MUTATIONS: dict = {}      # nombre -> meta
_SUBSCRIPTIONS: dict = {}  # nombre -> {evento, tipo}


def registrar_tipo(nombre, campos):
    _TIPOS[nombre] = list(campos)


def registrar_query(nombre, resolver, *, tipo, args=None, servicio=None, permiso=None, scopes=()):
    """Registra una query. `servicio` = ruta del servicio que la resuelve (obligatorio: garantiza
    que NO hay acceso directo a BD). `resolver(contexto, **args)` delega en ese servicio."""
    assert callable(resolver), f"resolver de {nombre} no es callable"
    assert servicio, f"la query '{nombre}' debe declarar su servicio de destino"
    _QUERIES[nombre] = {"resolver": resolver, "tipo": tipo, "args": dict(args or {}),
                        "servicio": servicio, "permiso": permiso, "scopes": tuple(scopes),
                        "clase": "query"}


def registrar_mutation(nombre, resolver, *, tipo, args=None, servicio=None, permiso=None, scopes=()):
    assert callable(resolver), f"resolver de {nombre} no es callable"
    assert servicio, f"la mutation '{nombre}' debe declarar su servicio de destino"
    _MUTATIONS[nombre] = {"resolver": resolver, "tipo": tipo, "args": dict(args or {}),
                          "servicio": servicio, "permiso": permiso, "scopes": tuple(scopes),
                          "clase": "mutation"}


def registrar_subscription(nombre, evento, *, tipo=None):
    """Subscription PREPARADA: mapea un tipo de evento del Corporate Event Bus a un canal GraphQL.
    Sin tiempo real todavía (Event Bus → Subscriptions → clientes GraphQL)."""
    _SUBSCRIPTIONS[nombre] = {"evento": evento, "tipo": tipo}


# ── getters ──────────────────────────────────────────────────────────────────
def tipos():
    return dict(_TIPOS)


def queries():
    return dict(_QUERIES)


def mutations():
    return dict(_MUTATIONS)


def subscriptions():
    return dict(_SUBSCRIPTIONS)


def query(nombre):
    return _QUERIES.get(nombre)


def mutation(nombre):
    return _MUTATIONS.get(nombre)


def operacion(nombre):
    return _QUERIES.get(nombre) or _MUTATIONS.get(nombre)


def limpiar():
    _TIPOS.clear(); _QUERIES.clear(); _MUTATIONS.clear(); _SUBSCRIPTIONS.clear()


__all__ = ["registrar_tipo", "registrar_query", "registrar_mutation", "registrar_subscription",
           "tipos", "queries", "mutations", "subscriptions", "query", "mutation", "operacion",
           "limpiar"]
