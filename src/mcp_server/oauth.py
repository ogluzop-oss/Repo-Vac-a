"""
Envoltura OAuth 2.1 (PKCE + Dynamic Client Registration) para el conector MCP de SOMA.

PRINCIPIO DE DISEÑO (task 2 del encargo): esto es una CÁSCARA de protocolo estándar alrededor de
la autenticación que Smart Manager YA tiene — JAMÁS un segundo motor de auth. El `/token` emite
los MISMOS access/refresh JWT que `seguridad.tokens.emitir_access/emitir_refresh` (los que ya
verifica `src.api.security`/`src.seguridad.tokens.verificar`), y `/authorize` valida credenciales
con la MISMA `db.usuario.validar_login_usuario` que usa el login de la REST API
(`src/api/routers/auth.py`) — reutilizada tal cual, incluida la decisión adaptativa de MFA
(`services.seguridad.mfa_decision`) para no abrir un atajo que se salte la política de la empresa.

Identidad de CLIENTE (DCR, RFC 7591): reutiliza `services.api_publica.developer` — la tabla
`api_dev_apps` ya modela "una app de terceros con client_id/secret/scopes/redirect_uri" y acepta
`id_empresa=NULL` (una app no atada a una empresa concreta, que es exactamente lo que es un
conector MCP registrado dinámicamente por Claude/ChatGPT: la empresa se decide en `/authorize`,
por el usuario que inicia sesión, no en el registro del cliente). Lo único que no existía en
ningún sitio es el código de autorización efímero de un solo uso — ver
`services.api_publica.mcp_oauth_codes` (migr. 0283) — porque hasta ahora NINGÚN flujo de auth de
este sistema usaba Authorization Code + PKCE (el login de la API es directo usuario+contraseña).

Endpoints (todos montados sin prefijo de blueprint; las rutas llevan el path completo):
    POST /mcp/oauth/register   — DCR (RFC 7591)
    GET  /mcp/oauth/authorize  — pantalla de login (reutiliza credenciales reales) + consentimiento
    POST /mcp/oauth/authorize  — procesa el login (y el 2º factor si la política lo exige)
    POST /mcp/oauth/token      — canje code+PKCE → JWT, y refresh_token → JWT nuevo
    POST /mcp/oauth/revoke     — RFC 7009
    GET  /.well-known/oauth-authorization-server  — metadatos (RFC 8414), para autodescubrimiento
    GET  /.well-known/oauth-protected-resource    — metadatos de recurso (RFC 9728)

PKCE es OBLIGATORIO (S256) en `/authorize` y `/token` — línea base de OAuth 2.1 — con independencia
de si el cliente manda `client_secret` (lo hace: nuestro DCR siempre emite uno, vía `developer.
registrar_app`; pero la seguridad real del intercambio de código la da el PKCE, no ese secret,
porque `/authorize` ocurre en un navegador que no puede guardar un secreto con garantías).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time

logger = logging.getLogger("mcp_server.oauth")

_HTML_LOGIN = """<!doctype html>
<html><head><meta charset="utf-8"><title>SOMA — Autorizar acceso</title>
<style>body{{font-family:sans-serif;max-width:420px;margin:48px auto;color:#222}}
input{{width:100%;padding:8px;margin:6px 0;box-sizing:border-box}}
button{{padding:8px 16px;background:#00665c;color:#fff;border:0;border-radius:4px;cursor:pointer}}
.error{{color:#b00020}}</style></head><body>
<h2>Autorizar acceso a Smart Manager</h2>
<p>La aplicación <b>{client_nombre}</b> solicita acceso a tu cuenta.</p>
{error_html}
<form method="post">
{campos_ocultos}
<label>Usuario</label><input name="usuario" autofocus required>
<label>Empresa (opcional)</label><input name="id_empresa">
<label>Contraseña</label><input name="password" type="password" required>
<button type="submit">Entrar y autorizar</button>
</form></body></html>"""

_HTML_MFA = """<!doctype html>
<html><head><meta charset="utf-8"><title>SOMA — Verificación adicional</title>
<style>body{{font-family:sans-serif;max-width:420px;margin:48px auto;color:#222}}
input{{width:100%;padding:8px;margin:6px 0;box-sizing:border-box}}
button{{padding:8px 16px;background:#00665c;color:#fff;border:0;border-radius:4px;cursor:pointer}}
.error{{color:#b00020}}</style></head><body>
<h2>Verificación en dos pasos</h2>
<p>Introduce el código de tu aplicación de autenticación.</p>
{error_html}
<form method="post">
{campos_ocultos}
<input type="hidden" name="mfa_token" value="{mfa_token}">
<label>Código</label><input name="codigo" autofocus required>
<button type="submit">Verificar</button>
</form></body></html>"""


def _b64url_sha256(valor: str) -> str:
    digest = hashlib.sha256(valor.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _campos_ocultos(campos: dict) -> str:
    from markupsafe import escape
    return "\n".join(f'<input type="hidden" name="{escape(k)}" value="{escape(v)}">'
                     for k, v in campos.items() if v is not None)


def _registrar_sesion_jwt(usuario: dict, refresh_token: str, jti: str, expira) -> None:
    """Persiste el refresh token (revocable) — mismo patrón que `api/routers/auth.py`."""
    try:
        from src.db import sesiones
        from src.seguridad import tokens
        sesiones.registrar(usuario["id"], jti, tokens.hash_refresh(refresh_token), expira,
                           id_empresa=usuario.get("id_empresa"))
    except Exception:
        pass  # best-effort, igual que el resto del sistema


def _emitir_tokens(usuario: dict, *, amr: list[str]) -> dict:
    from src.seguridad import tokens
    refresh_token, jti, expira = tokens.emitir_refresh(usuario)
    _registrar_sesion_jwt(usuario, refresh_token, jti, expira)
    access = tokens.emitir_access(usuario, amr=amr, auth_time=int(time.time()))
    return {"access_token": access, "token_type": "Bearer",
            "expires_in": tokens.ACCESO_MINUTOS * 60, "refresh_token": refresh_token}


def _well_known_issuer() -> str:
    from flask import request
    return request.host_url.rstrip("/")


def crear_blueprint():
    from flask import Blueprint, jsonify, redirect, request

    bp = Blueprint("mcp_oauth", __name__)

    # ── RFC 7591 — Dynamic Client Registration ──────────────────────────────────────────
    @bp.post("/mcp/oauth/register")
    def register():
        from src.services.api_publica import developer
        d = request.get_json(silent=True) or {}
        redirect_uris = d.get("redirect_uris") or []
        if not redirect_uris or not isinstance(redirect_uris, list):
            return jsonify({"error": "invalid_client_metadata",
                            "error_description": "redirect_uris es obligatorio (lista no vacía)"}), 400
        nombre = (d.get("client_name") or "Cliente MCP").strip()[:160]
        res = developer.registrar_app(nombre, id_empresa=None, scopes=["mcp"], sandbox=False,
                                      redirect_uri=redirect_uris[0])
        if not res.get("ok"):
            return jsonify({"error": "invalid_client_metadata",
                            "error_description": res.get("error", "error registrando el cliente")}), 400
        return jsonify({
            "client_id": res["client_id"],
            "client_secret": res["client_secret"],
            "client_id_issued_at": int(time.time()),
            "client_secret_expires_at": 0,
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
            "client_name": nombre,
            "scope": "mcp",
        }), 201

    # ── Authorization Code + PKCE: pantalla de login (reutiliza credenciales reales) ────────
    @bp.route("/mcp/oauth/authorize", methods=["GET", "POST"])
    def authorize():
        from src.services.api_publica import developer

        qs = request.values  # GET: query string; POST: query string + form, ambos disponibles
        response_type = qs.get("response_type")
        client_id = qs.get("client_id")
        redirect_uri = qs.get("redirect_uri")
        state = qs.get("state")
        code_challenge = qs.get("code_challenge")
        code_challenge_method = qs.get("code_challenge_method", "S256")
        scope = qs.get("scope")

        if response_type != "code":
            return jsonify({"error": "unsupported_response_type"}), 400
        app = developer.obtener_app(client_id) if client_id else None
        if not app or app.get("estado") != "activa":
            return jsonify({"error": "invalid_client"}), 400
        if not redirect_uri or redirect_uri != app.get("redirect_uri"):
            return jsonify({"error": "invalid_request",
                            "error_description": "redirect_uri no coincide con el registrado"}), 400
        if not code_challenge or code_challenge_method != "S256":
            # OAuth 2.1: PKCE (S256) obligatorio.
            return jsonify({"error": "invalid_request",
                            "error_description": "code_challenge (S256) es obligatorio"}), 400

        campos_oauth = {"response_type": response_type, "client_id": client_id,
                       "redirect_uri": redirect_uri, "state": state,
                       "code_challenge": code_challenge,
                       "code_challenge_method": code_challenge_method, "scope": scope}

        if request.method == "GET":
            return _HTML_LOGIN.format(client_nombre=app.get("nombre") or client_id,
                                      error_html="", campos_ocultos=_campos_ocultos(campos_oauth))

        # POST: puede ser el paso 1 (usuario+password) o el paso 2 (mfa_token+codigo).
        from src.db.usuario import validar_login_usuario
        from src.seguridad import tokens as _tokens

        mfa_token = request.form.get("mfa_token")
        if mfa_token:
            claims = _tokens.verificar(mfa_token, "mfa_pending")
            if not claims:
                return _HTML_LOGIN.format(client_nombre=app.get("nombre") or client_id,
                                          error_html='<p class="error">Sesión de verificación caducada, inicia de nuevo.</p>',
                                          campos_ocultos=_campos_ocultos(campos_oauth)), 401
            from src.services.seguridad import mfa as _mfa
            codigo = (request.form.get("codigo") or "").strip()
            uid = claims.get("sub")
            es_recovery = False
            ok = bool(_mfa.verificar(uid, codigo))
            if not ok:
                ok = es_recovery = bool(_mfa.usar_recovery_code(uid, codigo))
            if not ok:
                return _HTML_MFA.format(mfa_token=mfa_token, error_html='<p class="error">Código incorrecto.</p>',
                                        campos_ocultos=_campos_ocultos(campos_oauth)), 401
            usuario = {"id": claims.get("sub"), "id_empresa": claims.get("empresa"),
                      "centro_codigo": claims.get("tienda"), "perfil": claims.get("rol"),
                      "nombre": claims.get("nombre")}
            amr = "pwd,otp"
        else:
            usuario_in = (request.form.get("usuario") or "").strip()
            password = request.form.get("password") or ""
            id_empresa_in = (request.form.get("id_empresa") or "").strip() or None
            usuario = validar_login_usuario(usuario_in, password, id_empresa_in)
            if not usuario:
                return _HTML_LOGIN.format(client_nombre=app.get("nombre") or client_id,
                                          error_html='<p class="error">Credenciales incorrectas.</p>',
                                          campos_ocultos=_campos_ocultos(campos_oauth)), 401
            try:
                from src.services.seguridad import mfa_decision
                dec = mfa_decision.evaluar(usuario, id_empresa=usuario.get("id_empresa"))
            except Exception:
                dec = {"reto_requerido": False}
            if dec.get("reto_requerido"):
                mfa_token = _tokens.emitir_mfa_pending(usuario)
                return _HTML_MFA.format(mfa_token=mfa_token, error_html="",
                                        campos_ocultos=_campos_ocultos(campos_oauth))
            amr = "pwd"

        from src.services.api_publica import mcp_oauth_codes
        codigo_auth = mcp_oauth_codes.crear_codigo(
            client_id=client_id, id_usuario=usuario["id"], id_empresa=usuario.get("id_empresa"),
            redirect_uri=redirect_uri, code_challenge=code_challenge,
            code_challenge_method=code_challenge_method, scope=scope, amr=amr)

        from urllib.parse import urlencode
        sep = "&" if "?" in redirect_uri else "?"
        destino = f"{redirect_uri}{sep}{urlencode({'code': codigo_auth, 'state': state or ''})}"
        return redirect(destino, code=302)

    # ── Token endpoint: canjea código (PKCE) o refresca ─────────────────────────────────────
    @bp.post("/mcp/oauth/token")
    def token():
        from src.services.api_publica import developer

        d = request.form or request.get_json(silent=True) or {}
        grant_type = d.get("grant_type")

        if grant_type == "authorization_code":
            from src.services.api_publica import mcp_oauth_codes
            codigo = d.get("code")
            redirect_uri = d.get("redirect_uri")
            client_id = d.get("client_id")
            code_verifier = d.get("code_verifier")
            if not (codigo and redirect_uri and client_id and code_verifier):
                return jsonify({"error": "invalid_request",
                                "error_description": "faltan code/redirect_uri/client_id/code_verifier"}), 400
            app = developer.obtener_app(client_id)
            if not app or app.get("estado") != "activa":
                return jsonify({"error": "invalid_client"}), 401
            client_secret = d.get("client_secret")
            if client_secret and not developer.verificar_credenciales(client_id, client_secret):
                return jsonify({"error": "invalid_client"}), 401

            fila = mcp_oauth_codes.consumir_codigo(codigo, client_id=client_id, redirect_uri=redirect_uri)
            if not fila:
                return jsonify({"error": "invalid_grant",
                                "error_description": "código inválido, caducado, ya usado o reutilizado"}), 400
            if _b64url_sha256(code_verifier) != fila["code_challenge"]:
                return jsonify({"error": "invalid_grant", "error_description": "PKCE no verifica"}), 400

            from src.db.usuario import obtener_usuario
            usuario = obtener_usuario(fila["id_usuario"]) or {
                "id": fila["id_usuario"], "id_empresa": fila["id_empresa"]}
            amr = (fila.get("amr") or "pwd").split(",")
            cuerpo = _emitir_tokens(usuario, amr=amr)
            cuerpo["scope"] = fila.get("scope") or "mcp"
            return jsonify(cuerpo)

        if grant_type == "refresh_token":
            from src.seguridad import tokens as _tokens
            raw = d.get("refresh_token", "")
            claims = _tokens.verificar(raw, "refresh")
            if not claims:
                return jsonify({"error": "invalid_grant"}), 400
            try:
                from src.db import sesiones
                if not sesiones.es_valido(claims.get("jti"), _tokens.hash_refresh(raw)):
                    return jsonify({"error": "invalid_grant"}), 400
            except Exception:
                pass
            from src.db.usuario import obtener_usuario
            usuario = obtener_usuario(claims.get("sub")) or {
                "id": claims.get("sub"), "id_empresa": claims.get("empresa")}
            access = _tokens.emitir_access(usuario)
            return jsonify({"access_token": access, "token_type": "Bearer",
                            "expires_in": _tokens.ACCESO_MINUTOS * 60})

        return jsonify({"error": "unsupported_grant_type"}), 400

    # ── RFC 7009 — Revocation ────────────────────────────────────────────────────────────────
    @bp.post("/mcp/oauth/revoke")
    def revoke():
        from src.seguridad import tokens as _tokens
        d = request.form or request.get_json(silent=True) or {}
        raw = d.get("token", "")
        claims = _tokens.verificar(raw, "refresh")
        if claims and claims.get("jti"):
            try:
                from src.db import sesiones
                sesiones.revocar(claims["jti"])
            except Exception:
                pass
        # RFC 7009: responder 200 SIEMPRE, exista o no el token (no confirmar/negar su validez).
        return jsonify({})

    # ── Autodescubrimiento ───────────────────────────────────────────────────────────────────
    @bp.get("/.well-known/oauth-authorization-server")
    def metadata_as():
        issuer = _well_known_issuer()
        return jsonify({
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/mcp/oauth/authorize",
            "token_endpoint": f"{issuer}/mcp/oauth/token",
            "registration_endpoint": f"{issuer}/mcp/oauth/register",
            "revocation_endpoint": f"{issuer}/mcp/oauth/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        })

    @bp.get("/.well-known/oauth-protected-resource")
    def metadata_rs():
        issuer = _well_known_issuer()
        return jsonify({
            "resource": f"{issuer}/mcp",
            "authorization_servers": [issuer],
            "scopes_supported": ["mcp"],
            "bearer_methods_supported": ["header"],
        })

    return bp


__all__ = ["crear_blueprint"]
