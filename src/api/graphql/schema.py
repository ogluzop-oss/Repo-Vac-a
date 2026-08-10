"""
GraphQL Enterprise · Schema (Fase IV · Bloque 1). Ensambla el esquema desde el registry, genera el
SDL y ejecuta operaciones. DEGRADABLE: si en el futuro se instala una librería GraphQL (graphene/
strawberry/ariadne), este registry la alimenta; hoy expone un ejecutor propio ligero. El ejecutor
resuelve SIEMPRE vía servicios (nunca SQL) y aplica la cadena de middlewares (auth/tenant/RBAC/rate).
"""

from __future__ import annotations

from src.api.graphql import context as _context
from src.api.graphql import descriptor, middlewares, mutations, queries, registry, subscriptions

_CARGADO = False

# Tipos GraphQL adicionales de la Fase IV (los del descriptor se reutilizan tal cual).
_TIPOS_EXTRA = {
    "Plugin": ["clave", "nombre", "version", "estado", "autor"],
    "MarketItem": ["clave", "nombre", "version", "categoria", "autor", "firmado", "licencia"],
    "Health": ["status", "subsistemas"],
    "Message": ["id", "conversation_id", "canal", "cuerpo", "creado"],
    "TimelineEntry": ["com_id", "tipo", "fecha", "detalle"],
    "Kpi": ["codigo", "valor", "periodo"],
    "Job": ["clave", "estado", "frecuencia"],
    "Rule": ["clave", "estado", "prioridad"],
    "WorkflowInstance": ["id", "estado", "documento"],
    "CommerceDescriptor": ["plataforma", "version", "fase", "estado"],
    "Company": ["id", "nombre"], "Store": ["id", "nombre"], "User": ["id", "nombre", "perfil"],
    "Customer": ["id", "nombre"], "Supplier": ["id", "nombre"], "StockItem": ["codigo", "stock"],
    "Product": ["codigo", "nombre"], "Order": ["id", "estado"], "Invoice": ["id", "total"],
}


def cargar():
    """Registra tipos, queries, mutations y subscriptions (idempotente)."""
    global _CARGADO
    if _CARGADO:
        return
    for nombre, campos in descriptor.TIPOS.items():
        registry.registrar_tipo(nombre, campos)
    for nombre, campos in _TIPOS_EXTRA.items():
        registry.registrar_tipo(nombre, campos)
    queries.registrar_todo()
    mutations.registrar_todo()
    subscriptions.registrar_todo()
    _CARGADO = True


def esquema() -> dict:
    """Descriptor completo del esquema (tipos + operaciones + servicio de destino de cada una)."""
    cargar()
    def _ops(d):
        return {n: {"tipo": m["tipo"], "args": m["args"], "servicio": m["servicio"],
                    "permiso": m["permiso"]} for n, m in d.items()}
    return {"tipos": registry.tipos(), "queries": _ops(registry.queries()),
            "mutations": _ops(registry.mutations()), "subscriptions": registry.subscriptions()}


def _sdl_args(args):
    if not args:
        return ""
    return "(" + ", ".join(f"{k}: {v}" for k, v in args.items()) + ")"


def sdl() -> str:
    """Genera el SDL (Schema Definition Language) del esquema previsto."""
    cargar()
    lineas = []
    for nombre, campos in registry.tipos().items():
        lineas.append(f"type {nombre} {{")
        for c in campos:
            lineas.append(f"  {c}: String")
        lineas.append("}")
    lineas.append("type Query {")
    for n, m in registry.queries().items():
        lineas.append(f"  {n}{_sdl_args(m['args'])}: {m['tipo']}")
    lineas.append("}")
    lineas.append("type Mutation {")
    for n, m in registry.mutations().items():
        lineas.append(f"  {n}{_sdl_args(m['args'])}: {m['tipo']}")
    lineas.append("}")
    lineas.append("type Subscription {")
    for n, s in registry.subscriptions().items():
        lineas.append(f"  {n}: {s.get('tipo') or 'JSON'}")
    lineas.append("}")
    return "\n".join(lineas)


def ejecutar(operacion, args=None, contexto=None) -> dict:
    """Ejecuta una query o mutation por nombre. Aplica middlewares y delega en el servicio.
    Respuesta estilo GraphQL: {"data": {op: ...}} | {"errors": [{...}]}."""
    cargar()
    ctx = _context.desde_dict(contexto) if isinstance(contexto, dict) else (contexto or {})
    meta = registry.operacion(operacion)
    if not meta:
        return {"errors": [{"codigo": "unknown_operation", "mensaje": operacion}]}
    ok, err = middlewares.aplicar(meta, ctx, clave=operacion)
    if not ok:
        return {"errors": [err]}
    try:
        datos = meta["resolver"](ctx, **(args or {}))
        return {"data": {operacion: datos}}
    except Exception as e:
        return {"errors": [{"codigo": "resolver_error", "mensaje": str(e)}]}


__all__ = ["cargar", "esquema", "sdl", "ejecutar"]
