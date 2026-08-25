"""Router /customers — directorio de clientes (solo lectura). Consume `src.services.clientes`."""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/customers")
    @requiere_auth("clientes.ver")
    def customers_listar():
        from flask import g, jsonify, request
        from src.services import clientes
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 50))
        res = clientes.buscar(g.ctx["id_empresa"], request.args.get("q", ""), limite=limite)
        return jsonify(envolver(res, p))

    @bp.get("/customers/<int:cliente_id>")
    @requiere_auth("clientes.ver")
    def customers_obtener(cliente_id):
        from flask import g, jsonify
        from src.services import clientes
        c = clientes.obtener(g.ctx["id_empresa"], cliente_id)
        return (jsonify(c), 200) if c else (jsonify({"error": "no encontrado"}), 404)
