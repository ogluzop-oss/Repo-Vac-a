"""Router /system — salud y versión (público) + estado operacional unificado (autenticado, F2)."""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/system/health")
    def health():
        from flask import jsonify
        estado = {"status": "ok"}
        try:
            from src.services.observabilidad import health as H
            if hasattr(H, "estado"):
                estado = H.estado()
            elif hasattr(H, "salud"):
                estado = H.salud()
        except Exception:
            pass
        return jsonify(estado)

    @bp.get("/system/version")
    def version():
        from flask import jsonify
        return jsonify({"name": "Smart Manager AI", "api": "v1", "plataforma": "Enterprise"})

    # ── Health checks estándar de orquestador (Fase cloud): liveness / readiness / version. PÚBLICOS,
    #    sin información sensible, reutilizan observabilidad.health (NO crea mecanismos nuevos). El código
    #    HTTP permite a un balanceador/orquestador (k8s, LB) decidir tráfico: 200=ok, 503=no listo. ──
    @bp.get("/health/live")
    def health_live():
        from flask import jsonify
        try:
            from src.services.observabilidad import health as H
            r = H.live()
        except Exception:
            r = {"status": "ok"}
        return jsonify(r), 200   # liveness: si el proceso responde, está vivo

    @bp.get("/health/ready")
    def health_ready():
        from flask import jsonify
        try:
            from src.services.observabilidad import health as H
            r = H.ready()
        except Exception:
            r = {"status": "unavailable"}
        return jsonify(r), (200 if r.get("status") == "ok" else 503)

    @bp.get("/health/version")
    def health_version():
        from flask import jsonify
        return jsonify({"name": "Smart Manager AI", "api": "v1"})

    # ── Estado operacional unificado (F2): reutiliza observabilidad.estado. Autenticado; el tenant
    #    sale SIEMPRE del token (aislamiento). No crea mecanismos nuevos: compone los existentes. ──
    @bp.get("/system/status")
    @requiere_auth()
    def status():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        return jsonify({"global": estado.global_(),
                        "modulos": estado.por_modulo(g.ctx["id_empresa"])})

    @bp.get("/system/status/tenant")
    @requiere_auth()
    def status_tenant():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        return jsonify(estado.por_tenant(g.ctx["id_empresa"]))

    @bp.get("/system/selftest")
    @requiere_auth()
    def selftest():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        r = estado.self_test(g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 503)

    @bp.get("/system/diagnostico")
    @requiere_auth()
    def diagnostico():
        from flask import g, jsonify
        from src.services.observabilidad import estado
        return jsonify(estado.diagnostico(g.ctx["id_empresa"]))
