"""
Router /documents — registro documental (solo lectura de metadatos). Consume
`src.services.documentos`. La descarga del fichero queda fuera de alcance por ahora (ver docstring
del servicio).
"""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/documents")
    @requiere_auth("documentos.ver")
    def documents_listar():
        from flask import g, jsonify, request
        from src.services import documentos
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 200))
        res = documentos.buscar(g.ctx["id_empresa"], request.args.get("q", ""),
                                tipo=request.args.get("tipo"), limite=limite)
        return jsonify(envolver(res, p))

    @bp.get("/documents/<id_documento>")
    @requiere_auth("documentos.ver")
    def documents_obtener(id_documento):
        from flask import g, jsonify
        from src.services import documentos
        doc = documentos.obtener(g.ctx["id_empresa"], id_documento)
        return (jsonify(doc), 200) if doc else (jsonify({"error": "no encontrado"}), 404)
