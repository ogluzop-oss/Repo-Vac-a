"""Router /suppliers — directorio de proveedores (solo lectura). Consume `src.services.proveedores`."""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/suppliers")
    @requiere_auth("proveedores.ver")
    def suppliers_listar():
        from flask import g, jsonify, request
        from src.services import proveedores
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 50))
        res = proveedores.buscar(g.ctx["id_empresa"], request.args.get("q", ""), limite=limite)
        return jsonify(envolver(res, p))

    @bp.get("/suppliers/<int:proveedor_id>")
    @requiere_auth("proveedores.ver")
    def suppliers_obtener(proveedor_id):
        from flask import g, jsonify
        from src.services import proveedores
        p = proveedores.obtener(g.ctx["id_empresa"], proveedor_id)
        return (jsonify(p), 200) if p else (jsonify({"error": "no encontrado"}), 404)
