"""Router /campaigns — consume el Campaign Manager (CCP B3)."""

from src.api.paginacion import envolver
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/campaigns")
    @requiere_auth()
    def campaigns_listar():
        from flask import g, jsonify, request
        from src.services import ccp
        return jsonify(envolver(ccp.campanas.listar_campanas(
            g.ctx["id_empresa"], estado=request.args.get("estado"))))

    @bp.post("/campaigns")
    @requiere_auth("campanas.crear")
    def campaigns_crear():
        from flask import g, jsonify, request
        d = request.get_json(silent=True) or {}
        from src.services import ccp
        cid = ccp.campanas.crear_campana(
            d.get("nombre", "Campaña"), id_empresa=g.ctx["id_empresa"], tipo=d.get("tipo", "aviso"),
            asunto=d.get("asunto", ""), cuerpo=d.get("cuerpo", ""),
            destinatarios=d.get("destinatarios"), resolver=d.get("resolver"))
        return jsonify({"id": cid}), (201 if cid else 400)

    @bp.post("/campaigns/<int:cid>/process")
    @requiere_auth("campanas.crear")
    def campaigns_procesar(cid):
        from flask import jsonify
        from src.services import ccp
        n = ccp.campanas.procesar_campana(cid)
        return jsonify({"procesadas": n, "estadisticas": ccp.campanas.estadisticas(cid)})
