"""
Seguridad de la Enterprise REST API (Fase III · B2).

Reutiliza la infraestructura existente: JWT (`seguridad.tokens`), rate limit (`seguridad.rate_limit`),
RBAC (`services.autorizacion`) y aislamiento por tenant (el `id_empresa` sale SIEMPRE del token/clave,
nunca del cuerpo). API Keys por entorno para integraciones máquina-a-máquina. No accede a la BD directa.
"""

import functools
import logging
import os

logger = logging.getLogger("api.security")


def _jwt_contexto(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    try:
        from src.seguridad import tokens
        claims = tokens.verificar(auth_header[7:], "access")
    except Exception:
        claims = None
    if not claims:
        return None
    return {"usuario": {"id": claims.get("sub"), "id_empresa": claims.get("empresa"),
                        "perfil": claims.get("rol"), "nombre": claims.get("nombre")},
            "id_empresa": claims.get("empresa"), "auth": "jwt", "claims": claims}


def _apikey_contexto(api_key, empresa_header):
    """API Key máquina-a-máquina: la clave maestra (env API_MASTER_KEY) + cabecera X-Empresa-Id fijan
    el tenant. Preparado para un catálogo de claves por empresa en el futuro."""
    maestra = os.getenv("API_MASTER_KEY")
    if not (api_key and maestra and api_key == maestra and empresa_header):
        return None
    return {"usuario": {"id": "api", "id_empresa": empresa_header, "perfil": "API"},
            "id_empresa": empresa_header, "auth": "apikey"}


def contexto_de_request():
    """Devuelve el contexto autenticado {usuario, id_empresa, auth} o None. Tenant = del token/clave."""
    from flask import request
    ctx = _jwt_contexto(request.headers.get("Authorization"))
    if ctx:
        return ctx
    return _apikey_contexto(request.headers.get("X-API-Key"), request.headers.get("X-Empresa-Id"))


def requiere_auth(permiso=None, *, limite=240, ventana=60):
    """Decorador: exige autenticación (JWT/API Key), aplica rate limit y, opcionalmente, RBAC."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            from flask import g, jsonify, request
            # Rate limit por IP + ruta.
            try:
                from src.seguridad import rate_limit
                clave = f"{request.remote_addr or '?'}:{request.path}"
                if not rate_limit.permitido(clave, limite, ventana):
                    return jsonify({"error": "rate_limited"}), 429
            except Exception:
                pass
            ctx = contexto_de_request()
            if not ctx or not ctx.get("id_empresa"):
                return jsonify({"error": "unauthorized"}), 401
            g.ctx = ctx
            if permiso and (ctx["usuario"].get("perfil") not in ("ADMINISTRADOR", "API")):
                try:
                    from src.services import autorizacion
                    if not autorizacion.puede(ctx["usuario"], permiso, id_empresa=ctx["id_empresa"]):
                        return jsonify({"error": "forbidden", "permiso": permiso}), 403
                except Exception:
                    pass   # si RBAC no está disponible, no bloquea (degradable)
            return fn(*a, **k)
        return wrapper
    return deco


def requiere_step_up(accion=None, *, permiso=None, max_edad=300, limite=120, ventana=60):
    """Decorador para endpoints SENSIBLES: además de autenticación + RBAC, exige que la identidad
    HUMANA tenga MFA reciente (step-up). La recencia se DERIVA del token real (`mfa`+`auth_time`), nunca
    de un booleano del cliente. Las API keys / M2M (`auth='apikey'`) pasan (identidad de servicio, con
    su propio RBAC) — Regla 3. Es el guard oficial de step-up para REST/GraphQL (equivalente conceptual
    a `pedir_step_up` en escritorio; ambos consultan `mfa_stepup`/política)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            from flask import g, jsonify, request
            try:
                from src.seguridad import rate_limit
                clave = f"{request.remote_addr or '?'}:{request.path}"
                if not rate_limit.permitido(clave, limite, ventana):
                    return jsonify({"error": "rate_limited"}), 429
            except Exception:
                pass
            ctx = contexto_de_request()
            if not ctx or not ctx.get("id_empresa"):
                return jsonify({"error": "unauthorized"}), 401
            g.ctx = ctx
            # M2M / API key: identidad de servicio → sin MFA humano (Regla 3).
            if ctx.get("auth") == "apikey":
                return fn(*a, **k)
            usuario = ctx["usuario"]
            emp = ctx["id_empresa"]
            # RBAC del permiso lógico si se indica.
            if permiso and usuario.get("perfil") not in ("ADMINISTRADOR", "API"):
                try:
                    from src.services import autorizacion
                    if not autorizacion.puede(usuario, permiso, id_empresa=emp):
                        return jsonify({"error": "forbidden", "permiso": permiso}), 403
                except Exception:
                    pass
            from src.seguridad import tokens
            claims = ctx.get("claims") or {}
            if not tokens.mfa_reciente(claims, max_edad):
                try:
                    from src.services.seguridad import mfa_eventos
                    mfa_eventos.emitir("STEP_UP_REQUIRED", id_usuario=usuario.get("id"), id_empresa=emp,
                                       detalle=f"accion={accion or request.path}")
                except Exception:
                    pass
                # Semántica: sin MFA en absoluto (debe enrolar) vs. MFA no reciente (step-up).
                motivo = "mfa_enrollment_required" if not claims.get("mfa") else "step_up_required"
                return jsonify({"error": motivo, "accion": accion}), 401
            return fn(*a, **k)
        return wrapper
    return deco
