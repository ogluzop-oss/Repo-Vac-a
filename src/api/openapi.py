"""
OpenAPI/Swagger de la Enterprise REST API (Fase III · B2).

Genera el documento OpenAPI 3.0 a partir de las rutas registradas y sirve Swagger UI en `/docs`.
Versionado y esquemas de seguridad (bearer JWT + API Key) declarados.
"""

_SWAGGER_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Smart Manager API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css"></head>
<body><div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
<script>window.onload=()=>SwaggerUIBundle({url:'openapi.json',dom_id:'#swagger-ui'});</script>
</body></html>"""


def _spec(url_prefix):
    from flask import current_app
    paths = {}
    for rule in current_app.url_map.iter_rules():
        ruta = str(rule)
        if not ruta.startswith(url_prefix):
            continue
        p = ruta[len(url_prefix):] or "/"
        p = p.replace("<int:", "{").replace("<", "{").replace(">", "}")
        entry = paths.setdefault(p, {})
        for m in (rule.methods or set()):
            if m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                op = {"summary": rule.endpoint.split(".")[-1],
                      "security": [{"bearerAuth": []}, {"apiKey": []}],
                      "responses": {"200": {"description": "OK"},
                                    "401": {"description": "No autorizado"}}}
                if m == "GET":
                    # Convención E1: parámetros de paginación/orden/filtrado (opcionales).
                    from src.api import paginacion
                    op["parameters"] = paginacion.openapi_parametros()
                entry[m.lower()] = op
    return {
        "openapi": "3.0.0",
        "info": {"title": "Smart Manager AI API", "version": "v1",
                 "description": "Enterprise REST API — consume servicios (API-First, multiempresa)."},
        "servers": [{"url": url_prefix}],
        "paths": paths,
        "components": {"securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
            "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}},
    }


def registrar(bp, url_prefix="/api/v1"):
    @bp.get("/openapi.json")
    def openapi_json():
        from flask import jsonify
        return jsonify(_spec(url_prefix))

    @bp.get("/docs")
    def docs():
        return _SWAGGER_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}
