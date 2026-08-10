"""Router /auth — login/refresh (JWT) + MFA humano. Consume `db.usuario` + `seguridad.tokens` +
`services.seguridad.mfa`/`mfa_politica`/`mfa_eventos`.

MFA en la API humana (Fase 2 — cierra el bypass): si el usuario tiene 2º factor ACTIVO, `/auth/login`
NO emite un JWT completo; devuelve `mfa_required` + un token TEMPORAL `mfa_token` (type='mfa_pending',
que los endpoints protegidos rechazan). El JWT completo solo se emite en `/auth/mfa` tras validar el
segundo factor (TOTP o recovery code).

Convención de claims (decisión documentada): el access token lleva `amr` (OIDC Authentication Methods
References) = `["pwd"]` (solo credenciales) o `["pwd","otp"]` (credenciales + segundo factor), y un
booleano de conveniencia `mfa`. Las API keys / M2M NO pasan por MFA (otra ruta de auth).
"""


def registrar(bp):
    @bp.post("/auth/login")
    def login():
        from flask import jsonify, request
        d = request.get_json(silent=True) or {}
        from src.db.usuario import validar_login_usuario
        u = validar_login_usuario(d.get("usuario"), d.get("password"), d.get("id_empresa"))
        if not u:
            return jsonify({"error": "invalid_credentials"}), 401
        from src.seguridad import tokens
        # Decisión ADAPTATIVA de MFA (Fase 6): política empresa → override rol → factor activo.
        try:
            from src.services.seguridad import mfa_decision
            dec = mfa_decision.evaluar(u, id_empresa=u.get("id_empresa"))
        except Exception:
            dec = {"reto_requerido": False, "debe_enrolar": False}
        if dec.get("reto_requerido"):
            try:
                from src.services.seguridad import mfa_eventos
                mfa_eventos.emitir("MFA_CHALLENGE", id_usuario=u.get("id"),
                                   id_empresa=u.get("id_empresa"), detalle="api")
            except Exception:
                pass
            # Autenticación PARCIAL: no se emite access/refresh hasta completar el 2º factor.
            return jsonify({"mfa_required": True, "mfa_token": tokens.emitir_mfa_pending(u),
                            "usuario": u.get("nombre")})
        # Sin 2º factor activo. Si la política OBLIGA (empresa/rol/suelo crítico) pero el usuario no lo
        # tiene, se SEÑALA (sin bloquear el acceso por API para no dejar fuera a nadie; el enrolamiento
        # es de UI). No es un bypass del MFA activo (ese caso ya se atendió arriba).
        import time as _time
        resp = {"access": tokens.emitir_access(u, amr=["pwd"], auth_time=int(_time.time()),
                                               enrollment_required=bool(dec.get("debe_enrolar"))),
                "refresh": tokens.emitir_refresh(u)[0],
                "empresa": u.get("id_empresa"), "usuario": u.get("nombre")}
        if dec.get("debe_enrolar"):
            resp["mfa_enrollment_required"] = True
        return jsonify(resp)

    @bp.post("/auth/mfa")
    def auth_mfa():
        from flask import jsonify, request
        d = request.get_json(silent=True) or {}
        from src.seguridad import tokens
        claims = tokens.verificar(d.get("mfa_token", ""), "mfa_pending")
        if not claims:
            return jsonify({"error": "invalid_token"}), 401
        uid = claims.get("sub")
        codigo = (d.get("codigo") or "").strip()
        from src.services.seguridad import mfa, mfa_eventos
        # Anti fuerza bruta del 2º factor: 5 intentos / 5 min por usuario (Fase 3).
        try:
            from src.seguridad import rate_limit
            if not rate_limit.permitido(f"mfa_verify:{uid}", limite=5, ventana_seg=300):
                mfa_eventos.emitir("MFA_FAILURE", id_usuario=uid, id_empresa=claims.get("empresa"),
                                   detalle="rate_limited")
                return jsonify({"error": "rate_limited"}), 429
        except Exception:
            pass
        # Distingue TOTP de recovery code (auditoría + consumo del código de un solo uso).
        es_recovery = False
        ok = bool(mfa.verificar(uid, codigo))
        if not ok:
            es_recovery = bool(mfa.usar_recovery_code(uid, codigo))
            ok = es_recovery
        if not ok:
            mfa_eventos.emitir("MFA_FAILURE", id_usuario=uid, id_empresa=claims.get("empresa"),
                               detalle="api")
            return jsonify({"error": "invalid_mfa"}), 401
        mfa_eventos.emitir("MFA_RECOVERY_USED" if es_recovery else "MFA_SUCCESS",
                           id_usuario=uid, id_empresa=claims.get("empresa"), detalle="api")
        u = {"id": uid, "id_empresa": claims.get("empresa"), "tienda_id": claims.get("tienda"),
             "perfil": claims.get("rol"), "nombre": claims.get("nombre")}
        import time as _time
        return jsonify({"access": tokens.emitir_access(u, amr=["pwd", "otp"],
                                                       auth_time=int(_time.time())),
                        "refresh": tokens.emitir_refresh(u)[0],
                        "empresa": u.get("id_empresa"), "usuario": u.get("nombre")})

    @bp.post("/auth/step-up")
    def auth_step_up():
        """Refresca la RECENCIA de MFA de un usuario humano ya autenticado (para acciones críticas de
        API): con un access token válido + un 2º factor (TOTP/recovery según política) emite un access
        nuevo con `auth_time` actualizado. No aplica a API keys / M2M."""
        from flask import jsonify, request
        from src.api.security import contexto_de_request
        ctx = contexto_de_request()
        if not ctx or ctx.get("auth") != "jwt":
            return jsonify({"error": "unauthorized"}), 401
        d = request.get_json(silent=True) or {}
        us = ctx["usuario"]
        claims = ctx.get("claims") or {}
        uid = us.get("id")
        emp = ctx.get("id_empresa")
        try:
            from src.seguridad import rate_limit
            if not rate_limit.permitido(f"stepup:{uid}", 5, 300):
                return jsonify({"error": "rate_limited"}), 429
        except Exception:
            pass
        from src.services.seguridad import mfa_stepup
        if not mfa_stepup.verificar(uid, (d.get("codigo") or "").strip(), id_empresa=emp,
                                    accion=d.get("accion")):
            return jsonify({"error": "invalid_mfa"}), 401
        import time as _time

        from src.seguridad import tokens
        u = {"id": uid, "id_empresa": emp, "tienda_id": claims.get("tienda"),
             "perfil": us.get("perfil"), "nombre": us.get("nombre")}
        return jsonify({"access": tokens.emitir_access(u, amr=["pwd", "otp"],
                                                       auth_time=int(_time.time()))})

    @bp.post("/auth/refresh")
    def refresh():
        from flask import jsonify, request
        d = request.get_json(silent=True) or {}
        from src.seguridad import tokens
        claims = tokens.verificar(d.get("refresh", ""), "refresh")
        if not claims:
            return jsonify({"error": "invalid_token"}), 401
        u = {"id": claims.get("sub"), "id_empresa": claims.get("empresa")}
        return jsonify({"access": tokens.emitir_access(u)})
