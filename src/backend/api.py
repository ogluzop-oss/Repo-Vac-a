"""
API REST de Smart Manager AI (A1) — blueprint versionado `/api/v1`.

Principios:
- **Capa de exposición fina**: toda la lógica vive en los servicios existentes
  (usuario, seguridad/tokens, sesiones, catálogo, online_orders…); aquí solo se
  traduce HTTP↔servicio.
- **Autenticación JWT** (C1.4): login/refresh/logout con access+refresh; el refresh
  se persiste *hasheado* y es revocable (`sesiones`).
- **Aislamiento multi-tenant (A4)**: `@token_requerido` fija el `TenantContext` del
  hilo desde los claims (empresa/tienda) y lo restaura al terminar la petición →
  imposible operar fuera del tenant del token, incluso bajo concurrencia.
- **CORS configurable por entorno** (`API_CORS_ORIGINS`, lista blanca; NUNCA `*`).

Versionado: el prefijo `/api/v1` es estable. Cambios incompatibles → nuevo
blueprint `/api/v2` conviviendo con `/api/v1` (deprecación anunciada) para no
romper clientes existentes. Ver docs/api.md.

Flask se importa de forma perezosa en `crear_blueprint_api` (igual que el storefront).
"""

import logging
import os

logger = logging.getLogger("backend.api")

API_VERSION = "v1"


def _origenes_cors():
    return [o.strip() for o in os.getenv("API_CORS_ORIGINS", "").split(",") if o.strip()]


def crear_blueprint_api():
    from functools import wraps

    from flask import Blueprint, g, jsonify, request

    bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

    def _err(mensaje, codigo):
        return jsonify({"error": mensaje}), codigo

    # ── CORS (lista blanca por entorno; nunca abierto en producción) ──────────
    @bp.before_request
    def _preflight():
        if request.method == "OPTIONS":
            return ("", 204)

    @bp.after_request
    def _cors(resp):
        origin = request.headers.get("Origin")
        if origin and origin in _origenes_cors():
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    # ── Middleware de autenticación + contexto de tenant (A4) ─────────────────
    def token_requerido(f):
        @wraps(f)
        def envoltorio(*args, **kwargs):
            from src.seguridad import tokens
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return _err("token de acceso requerido", 401)
            datos = tokens.verificar(auth[7:], tipo="access")
            if not datos:
                return _err("token inválido o expirado", 401)
            from src.db.empresa import contexto_tenant
            # Fija el tenant SOLO para este hilo/petición (aislamiento real).
            with contexto_tenant(datos.get("empresa"), datos.get("tienda")):
                g.usuario = {"id": datos.get("sub"), "rol": datos.get("rol"),
                             "empresa": datos.get("empresa"), "tienda": datos.get("tienda"),
                             "nombre": datos.get("nombre")}
                return f(*args, **kwargs)
        return envoltorio

    bp.token_requerido = token_requerido      # disponible para los endpoints (A1.2)

    # ── Info / versión (público) ──────────────────────────────────────────────
    @bp.get("/")
    def info():
        return jsonify({"servicio": "smart-manager-api", "version": API_VERSION})

    # ── Autenticación ─────────────────────────────────────────────────────────
    @bp.post("/auth/login")
    def login():
        from src.db import sesiones
        from src.db import usuario as U
        from src.seguridad import tokens
        d = request.get_json(silent=True) or {}
        ident = (d.get("usuario") or d.get("email") or "").strip()
        pw = d.get("password") or ""
        empresa = d.get("empresa")            # opcional: id_empresa para desambiguar
        if not ident or not pw:
            return _err("usuario/email y password son obligatorios", 400)
        u = U.validar_login_usuario(ident, pw, id_empresa=empresa)
        if not u:
            return _err("credenciales inválidas o cuenta bloqueada", 401)
        access = tokens.emitir_access(u)
        refresh, jti, expira = tokens.emitir_refresh(u)
        sesiones.registrar(u["id"], jti, tokens.hash_refresh(refresh), expira,
                           id_empresa=u.get("id_empresa"))
        return jsonify({
            "access": access, "refresh": refresh,
            "usuario": {"id": u["id"], "nombre": u["nombre"], "rol": u["perfil"],
                        "empresa": u.get("id_empresa"), "tienda": u.get("tienda_id")},
        })

    @bp.post("/auth/refresh")
    def refresh():
        from src.db import sesiones
        from src.db import usuario as U
        from src.seguridad import tokens
        d = request.get_json(silent=True) or {}
        tok = d.get("refresh") or ""
        datos = tokens.verificar(tok, tipo="refresh")
        if not datos:
            return _err("refresh token inválido o expirado", 401)
        if not sesiones.es_valido(datos.get("jti"), tokens.hash_refresh(tok)):
            return _err("sesión revocada o caducada", 401)
        # Recarga el usuario para reflejar rol/tienda ACTUALES en el nuevo access.
        u = U.obtener_usuario(datos.get("sub"))
        if not u:
            return _err("usuario no disponible", 401)
        return jsonify({"access": tokens.emitir_access(u)})

    @bp.post("/auth/logout")
    def logout():
        from src.db import sesiones
        from src.seguridad import tokens
        d = request.get_json(silent=True) or {}
        tok = d.get("refresh") or ""
        if tok:
            datos = tokens.verificar(tok, tipo="refresh")
            if datos and datos.get("jti"):
                sesiones.revocar(datos["jti"])
        return jsonify({"ok": True})

    @bp.get("/auth/me")
    @token_requerido
    def me():
        return jsonify({"usuario": g.usuario})

    # ── Catálogo (solo lectura) — A1.2 ────────────────────────────────────────
    # La vista (pública/operativa) depende del rol; el aislamiento por empresa lo
    # aplica el servicio usando el TenantContext fijado por @token_requerido.
    @bp.get("/catalogo/productos")
    @token_requerido
    def api_productos():
        from src.services import catalogo as C
        interno = C.es_vista_interna(g.usuario.get("rol"))
        a = request.args
        prods = C.listar_productos(interno=interno, categoria=a.get("categoria", type=int),
                                   marca=a.get("marca", type=int), texto=a.get("texto"),
                                   limite=a.get("limite", default=200, type=int))
        return jsonify({"productos": prods, "total": len(prods)})

    @bp.get("/catalogo/productos/<int:pid>")
    @token_requerido
    def api_producto(pid):
        from src.services import catalogo as C
        p = C.producto(id_producto=pid, interno=C.es_vista_interna(g.usuario.get("rol")))
        if not p:
            return _err("producto no encontrado", 404)
        return jsonify(p)

    @bp.get("/catalogo/categorias")
    @token_requerido
    def api_categorias():
        from src.services import catalogo as C
        return jsonify({"categorias": C.listar_categorias(arbol=True, solo_visibles=False)})

    # ── Pedidos online (solo lectura) — A1.2 ──────────────────────────────────
    @bp.get("/pedidos")
    @token_requerido
    def api_pedidos():
        from src.services.tpv import online_orders_service as OS
        estado = request.args.get("estado")
        peds = OS.listar_pedidos_online(estado=estado)   # filtrado por tenant activo
        return jsonify({"pedidos": peds, "total": len(peds)})

    @bp.get("/pedidos/<pid>")
    @token_requerido
    def api_pedido(pid):
        from src.db.empresa import empresa_actual_id
        from src.services.tpv import online_orders_service as OS
        p = OS.obtener_pedido(pid)
        # Aislamiento explícito: solo se devuelve si pertenece al tenant del token.
        if not p or p.get("id_empresa") != empresa_actual_id():
            return _err("pedido no encontrado", 404)
        return jsonify(p)

    return bp
