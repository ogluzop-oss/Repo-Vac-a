"""Router /auth/webauthn — Passkeys / WebAuthn (Fase 5). Endpoints para la ceremonia del NAVEGADOR
(`navigator.credentials`): el cliente pide opciones (`begin`), ejecuta la ceremonia y envía la
respuesta (`finish`); el servidor (relying party) verifica con `services.seguridad.mfa_webauthn`.

Registro: requiere estar autenticado (access token). Login: usa el `mfa_token` (autenticación parcial)
emitido por `/auth/login`, como ALTERNATIVA al TOTP. WebAuthn es adicional; TOTP sigue como fallback.
Si la librería no está disponible, los endpoints devuelven `webauthn_unavailable` (501)."""


def registrar(bp):
    def _ctx_usuario():
        from src.api.security import contexto_de_request
        ctx = contexto_de_request()
        if not ctx:
            return None
        us = ctx.get("usuario") or {}
        return {"id": us.get("id") or us.get("sub"), "nombre": us.get("nombre"),
                "id_empresa": ctx.get("id_empresa")}

    @bp.post("/auth/webauthn/register/begin")
    def wa_reg_begin():
        from flask import jsonify
        u = _ctx_usuario()
        if not u:
            return jsonify({"error": "unauthorized"}), 401
        from src.services.seguridad import mfa_webauthn
        r = mfa_webauthn.iniciar_registro(u)
        if r.get("ok"):
            return jsonify(r)
        return jsonify(r), (501 if r.get("error") == "webauthn_unavailable" else 400)

    @bp.post("/auth/webauthn/register/finish")
    def wa_reg_finish():
        from flask import jsonify, request
        u = _ctx_usuario()
        if not u:
            return jsonify({"error": "unauthorized"}), 401
        d = request.get_json(silent=True) or {}
        from src.services.seguridad import mfa_webauthn
        r = mfa_webauthn.confirmar_registro(u, d.get("reto", ""), d.get("respuesta"),
                                            nombre=d.get("nombre"))
        return (jsonify(r), 200) if r.get("ok") else (jsonify(r), 400)

    @bp.post("/auth/webauthn/login/begin")
    def wa_login_begin():
        from flask import jsonify, request
        d = request.get_json(silent=True) or {}
        from src.seguridad import tokens
        claims = tokens.verificar(d.get("mfa_token", ""), "mfa_pending")
        if not claims:
            return jsonify({"error": "invalid_token"}), 401
        from src.services.seguridad import mfa_webauthn
        r = mfa_webauthn.iniciar_login({"id": claims.get("sub")})
        return (jsonify(r), 200) if r.get("ok") else (jsonify(r), 400)

    @bp.post("/auth/webauthn/login/finish")
    def wa_login_finish():
        from flask import jsonify, request
        d = request.get_json(silent=True) or {}
        from src.seguridad import tokens
        claims = tokens.verificar(d.get("mfa_token", ""), "mfa_pending")
        if not claims:
            return jsonify({"error": "invalid_token"}), 401
        uid = claims.get("sub")
        from src.services.seguridad import mfa_eventos, mfa_webauthn
        r = mfa_webauthn.confirmar_login({"id": uid}, d.get("reto", ""), d.get("respuesta"))
        if not r.get("ok"):
            mfa_eventos.emitir("MFA_FAILURE", id_usuario=uid, id_empresa=claims.get("empresa"),
                               detalle="webauthn")
            return jsonify(r), 401
        mfa_eventos.emitir("MFA_SUCCESS", id_usuario=uid, id_empresa=claims.get("empresa"),
                           detalle="webauthn")
        u = {"id": uid, "id_empresa": claims.get("empresa"), "tienda_id": claims.get("tienda"),
             "perfil": claims.get("rol"), "nombre": claims.get("nombre")}
        import time as _time
        return jsonify({"access": tokens.emitir_access(u, amr=["pwd", "webauthn"],
                                                       auth_time=int(_time.time())),
                        "refresh": tokens.emitir_refresh(u)[0],
                        "empresa": u.get("id_empresa"), "usuario": u.get("nombre")})
