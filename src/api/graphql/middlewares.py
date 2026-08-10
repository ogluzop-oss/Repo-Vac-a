"""
GraphQL Enterprise · Middlewares (Fase IV · Bloque 1). Cadena de seguridad que reutiliza EXACTAMENTE
la infraestructura REST: autenticación (JWT/API Key ya resueltos en el contexto), tenant obligatorio,
RBAC (`services.autorizacion`), scopes y rate limit (`seguridad.rate_limit`). No accede a la BD.
"""

from __future__ import annotations

from src.api.graphql import context as _ctx


def autenticar(contexto) -> tuple:
    """Exige contexto autenticado con tenant. (ok, error|None)."""
    if not contexto or not _ctx.id_empresa(contexto):
        return False, {"codigo": "unauthorized", "mensaje": "autenticación/tenant requeridos"}
    return True, None


def autorizar(contexto, permiso) -> tuple:
    """RBAC: ADMINISTRADOR/API pasan; el resto se evalúa con services.autorizacion (degradable)."""
    if not permiso:
        return True, None
    u = _ctx.usuario(contexto)
    if str(u.get("perfil", "")).upper() in ("ADMINISTRADOR", "API"):
        return True, None
    try:
        from src.services import autorizacion
        if autorizacion.puede(u, permiso, id_empresa=_ctx.id_empresa(contexto)):
            return True, None
        return False, {"codigo": "forbidden", "mensaje": f"permiso requerido: {permiso}"}
    except Exception:
        return True, None    # RBAC no disponible → no bloquea (degradable, como en REST)


def verificar_scopes(contexto, scopes) -> tuple:
    if not scopes:
        return True, None
    disponibles = set((contexto or {}).get("scopes") or ())
    if str((_ctx.usuario(contexto)).get("perfil", "")).upper() in ("ADMINISTRADOR", "API"):
        return True, None
    faltan = [s for s in scopes if s not in disponibles]
    if faltan:
        return False, {"codigo": "scope_requerido", "mensaje": f"scopes: {faltan}"}
    return True, None


def rate_limit(contexto, clave) -> tuple:
    try:
        from src.seguridad import rate_limit as _rl
        emp = _ctx.id_empresa(contexto) or "?"
        if not _rl.permitido(f"gql:{emp}:{clave}", 240, 60):
            return False, {"codigo": "rate_limited", "mensaje": "límite de peticiones superado"}
    except Exception:
        pass
    return True, None


def aplicar(meta, contexto, *, clave="") -> tuple:
    """Ejecuta la cadena completa para una operación (meta del registry). (ok, error|None)."""
    for check in (
        lambda: autenticar(contexto),
        lambda: rate_limit(contexto, clave or meta.get("servicio", "")),
        lambda: autorizar(contexto, meta.get("permiso")),
        lambda: verificar_scopes(contexto, meta.get("scopes")),
    ):
        ok, err = check()
        if not ok:
            return False, err
    return True, None


__all__ = ["autenticar", "autorizar", "verificar_scopes", "rate_limit", "aplicar"]
