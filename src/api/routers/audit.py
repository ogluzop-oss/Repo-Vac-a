"""Router /audit — consulta de eventos/replay (solo lectura). Se enriquece con el Audit Replay (B6)."""

from src.api.paginacion import envolver
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/audit/events")
    @requiere_auth()
    def eventos():
        from flask import g, jsonify, request
        from src.services import eventbus
        return jsonify(envolver(eventbus.replay(
            tipo=request.args.get("tipo"), id_empresa=g.ctx["id_empresa"])))

    @bp.get("/audit/replay")
    @requiere_auth()
    def replay():
        from flask import g, jsonify, request
        # Reconstrucción unificada (Audit Replay B6 si está; si no, eventos del bus).
        try:
            from src.services import audit_replay
            return jsonify(audit_replay.reconstruir(
                id_empresa=g.ctx["id_empresa"], com_id=request.args.get("com_id"),
                ref_entidad=request.args.get("entidad"), ref_id=request.args.get("id")))
        except Exception:
            from src.services import eventbus
            return jsonify({"eventos": eventbus.replay(id_empresa=g.ctx["id_empresa"])})
