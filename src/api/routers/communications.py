"""Router /communications y /conversations — consume el Corporate Communication Service (CCP)."""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.post("/communications")
    @requiere_auth("comunicaciones.enviar")
    def enviar():
        from flask import g, jsonify, request
        d = request.get_json(silent=True) or {}
        from src.services import ccp
        res = ccp.enviar_comunicacion(
            id_empresa=g.ctx["id_empresa"], destinatario=d.get("destinatario"),
            pistas=d.get("pistas"), asunto=d.get("asunto", ""), cuerpo=d.get("cuerpo", ""),
            plantilla=d.get("plantilla"), canal=d.get("canal"), contexto=d.get("contexto"),
            usuario=g.ctx["usuario"].get("nombre"))
        return jsonify(res.to_dict()), (200 if res.ok else 400)

    @bp.get("/communications")
    @requiere_auth()
    def historial():
        from flask import g, jsonify, request
        from src.services import ccp
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 100))
        return jsonify(envolver(ccp.historial_comunicaciones(
            g.ctx["id_empresa"], canal=request.args.get("canal"), limite=limite), p))

    @bp.get("/conversations")
    @requiere_auth()
    def conversaciones():
        from flask import g, jsonify, request
        from src.services import ccp
        return jsonify(envolver(ccp.conversaciones.listar_conversaciones(
            g.ctx["id_empresa"], correo=request.args.get("correo"))))
