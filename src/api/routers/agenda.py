"""
Router /agenda — calendario/agenda corporativa (eventos + participantes). Consume
`src.services.calendario` directamente: ya es la capa de servicio real, no hace falta una capa fina
adicional.

`GET /agenda` sin `desde`/`hasta` devuelve el mes en curso; con ambos, el rango pedido. Siempre
acotado a los eventos del usuario autenticado (creados por él o en los que participa).
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/agenda")
    @requiere_auth("calendario.gestionar")
    def agenda_listar():
        from datetime import date
        from flask import g, jsonify, request
        from src.services import calendario
        usuario_id = g.ctx["usuario"].get("id")
        desde, hasta = request.args.get("desde"), request.args.get("hasta")
        if desde and hasta:
            res = calendario.eventos_rango(desde, hasta, usuario=usuario_id,
                                           id_empresa=g.ctx["id_empresa"])
        else:
            hoy = date.today()
            res = calendario.eventos_mes(hoy.year, hoy.month, usuario=usuario_id,
                                         id_empresa=g.ctx["id_empresa"])
        return jsonify(res)

    @bp.post("/agenda")
    @requiere_auth("calendario.gestionar")
    def agenda_crear():
        from flask import g, jsonify, request
        from src.services import calendario
        d = request.get_json(silent=True) or {}
        if not d.get("titulo") or not d.get("inicio"):
            return jsonify({"error": "titulo e inicio son obligatorios"}), 400
        eid = calendario.crear_evento(
            d["titulo"], d["inicio"], fin=d.get("fin"), tipo=d.get("tipo", "evento"),
            descripcion=d.get("descripcion"), creado_por=g.ctx["usuario"].get("id"),
            participantes=d.get("participantes"), id_empresa=g.ctx["id_empresa"])
        return (jsonify({"id": eid}), 201) if eid else (jsonify({"error": "no se pudo crear"}), 400)
