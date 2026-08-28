"""
Enterprise REST API (Fase III · B2) — fachada de construcción.

`crear_api(v)` devuelve un Blueprint Flask versionado (`/api/<v>`) que SOLO consume servicios (nunca BD
directa). Montable en el backend Flask existente o en una app propia. API-First; multiempresa (tenant
del token). Capa limpia REST→servicios→dominio→BD (preparada para una futura capa GraphQL, B8).

    from src.api import crear_api
    app.register_blueprint(crear_api("v1"))
"""

import logging
import os

logger = logging.getLogger("api")


def _origenes_cors():
    return [o.strip() for o in os.getenv("API_CORS_ORIGINS", "").split(",") if o.strip()]


def _registrar_middleware(bp):
    """CORS (lista blanca por entorno; nunca `*`) + cabeceras de seguridad + correlation-id +
    métricas por petición. Portado del blueprint legacy `src.backend.api` al fusionar las dos APIs
    `/api/v1` que coexistían (ver ADR-0001) — aplica a TODOS los routers por igual."""
    from flask import request

    @bp.before_request
    def _preflight():
        if request.method == "OPTIONS":
            return ("", 204)

    @bp.before_request
    def _obs_inicio():
        try:
            import time
            from src.services.observabilidad import correlation, metricas
            cid = request.headers.get("X-Correlation-ID")
            correlation.set_id(cid or correlation.nuevo("api"))
            request.environ["_t_inicio"] = time.perf_counter()
            metricas.inc("sm_api_requests_total")
        except Exception:
            pass

    @bp.after_request
    def _cors_y_seguridad(resp):
        origin = request.headers.get("Origin")
        if origin and origin in _origenes_cors():
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Content-Security-Policy",
                                os.getenv("API_CSP", "default-src 'none'; frame-ancestors 'none'"))
        if os.getenv("API_HSTS", "1") == "1":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        try:
            import time
            from src.services.observabilidad import correlation, metricas
            resp.headers["X-Correlation-ID"] = correlation.get_id() or "-"
            if int(resp.status_code) >= 500:
                metricas.inc("sm_api_errores_total")
            t0 = request.environ.get("_t_inicio")
            if t0 is not None:
                metricas.observe("sm_api_latencia_segundos", time.perf_counter() - t0)
        except Exception:
            pass
        return resp


def _registrar_info(bp, version):
    """`/`, `/live`, `/ready`, `/metrics` a nivel de blueprint (fuera de cualquier router de
    recurso): son las rutas que usan las sondas de Kubernetes/Helm (`deploy/k8s`, `deploy/helm`) y
    deben existir tal cual, sin depender de qué routers de negocio estén registrados."""
    from flask import jsonify

    @bp.get("/")
    def _info():
        return jsonify({"servicio": "smart-manager-api", "version": version})

    @bp.get("/live")
    def _live():
        from src.services.observabilidad import health
        return jsonify(health.live())

    @bp.get("/ready")
    def _ready():
        from src.services.observabilidad import health
        r = health.ready()
        return jsonify(r), (200 if r.get("status") == "ok" else 503)

    @bp.get("/metrics")
    def _metrics():
        from flask import Response
        from src.services.observabilidad import metricas
        try:
            metricas.actualizar_negocio()
        except Exception:
            pass
        try:
            from src.services.observabilidad import operacional
            operacional.recolectar()
        except Exception:
            pass
        return Response(metricas.render(), mimetype="text/plain; version=0.0.4")


def crear_api(version: str = "v1"):
    """Blueprint de la API versionada."""
    from flask import Blueprint
    bp = Blueprint(f"api_{version}", __name__, url_prefix=f"/api/{version}")
    _registrar_middleware(bp)
    _registrar_info(bp, version)
    from src.api.routers import registrar_todos
    registrar_todos(bp)
    from src.api import openapi
    openapi.registrar(bp, url_prefix=f"/api/{version}")
    return bp


def crear_app():
    """App Flask autónoma con la API montada (útil para pruebas/servidor dedicado)."""
    from flask import Flask
    app = Flask("smart_manager_api")
    app.register_blueprint(crear_api("v1"))
    return app
