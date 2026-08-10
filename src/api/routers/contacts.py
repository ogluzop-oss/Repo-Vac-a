"""Router /contacts — consume el Recipient Resolution Service (destinatarios) vía la CCP."""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/contacts")
    @requiere_auth()
    def buscar():
        from flask import g, jsonify, request
        from src.services import ccp
        p = parametros()
        # Convención E1 (opt-in): al paginar, se lee lo suficiente para cubrir offset+limit; si no,
        # se conserva el comportamiento legacy (`limite`=25 por defecto).
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 25))
        res = ccp.buscar_destinatarios(g.ctx["id_empresa"], request.args.get("q", ""),
                                       contexto=request.args.get("contexto"), limite=limite)
        return jsonify(envolver([d.to_dict() for d in res], p))
