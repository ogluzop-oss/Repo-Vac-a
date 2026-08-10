"""Router /templates — consume el Corporate Templates Manager (CCP B1)."""

from src.api.paginacion import envolver
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/templates")
    @requiere_auth()
    def templates_listar():
        from flask import g, jsonify, request
        from src.services import ccp
        return jsonify(envolver(ccp.templates.listar_plantillas(
            g.ctx["id_empresa"], categoria=request.args.get("categoria"),
            idioma=request.args.get("idioma"), estado=request.args.get("estado"))))

    @bp.post("/templates")
    @requiere_auth("plantillas.editar")
    def templates_crear():
        from flask import g, jsonify, request
        d = request.get_json(silent=True) or {}
        from src.services import ccp
        pid = ccp.templates.crear_plantilla(
            d.get("codigo"), d.get("asunto", ""), d.get("cuerpo", ""), id_empresa=g.ctx["id_empresa"],
            categoria=d.get("categoria", "general"), idioma=d.get("idioma", "es"),
            formato=d.get("formato", "texto"), estado=d.get("estado", "borrador"))
        return jsonify({"id": pid}), (201 if pid else 400)
