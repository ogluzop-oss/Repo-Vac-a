"""
Enterprise REST API (Fase III · B2) — fachada de construcción.

`crear_api(v)` devuelve un Blueprint Flask versionado (`/api/<v>`) que SOLO consume servicios (nunca BD
directa). Montable en el backend Flask existente o en una app propia. API-First; multiempresa (tenant
del token). Capa limpia REST→servicios→dominio→BD (preparada para una futura capa GraphQL, B8).

    from src.api import crear_api
    app.register_blueprint(crear_api("v1"))
"""

import logging

logger = logging.getLogger("api")


def crear_api(version: str = "v1"):
    """Blueprint de la API versionada."""
    from flask import Blueprint
    bp = Blueprint(f"api_{version}", __name__, url_prefix=f"/api/{version}")
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
