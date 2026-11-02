"""
Router /notifications — notificaciones empresariales dirigidas al usuario autenticado (por id o por
rol). Consume `src.services.notificaciones` directamente: ya es la capa de servicio real (persistente,
multiempresa, auditada), no hace falta una capa fina adicional.
"""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/notifications")
    @requiere_auth("notificaciones.ver")
    def notifications_listar():
        from flask import g, jsonify, request
        from src.services import notificaciones
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 200))
        res = notificaciones.pendientes_usuario(
            g.ctx["usuario"], id_empresa=g.ctx["id_empresa"], limite=limite)
        return jsonify(envolver(res, p))

    @bp.post("/notifications/<int:id_notificacion>/leida")
    @requiere_auth("notificaciones.ver")
    def notifications_marcar_leida(id_notificacion):
        from flask import g, jsonify
        from src.services import notificaciones
        ok = notificaciones.marcar_leida(
            id_notificacion, g.ctx["usuario"].get("id"), id_empresa=g.ctx["id_empresa"])
        return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": "no se pudo marcar"}), 400)

    @bp.post("/notifications/device-token")
    @requiere_auth("notificaciones.ver")
    def notifications_registrar_token():
        from flask import g, jsonify, request
        from src.services.mobile import push
        d = request.get_json(silent=True) or {}
        token = (d.get("token") or "").strip()
        if not token:
            return jsonify({"error": "token requerido"}), 400
        ok = push.registrar_dispositivo(
            g.ctx["usuario"].get("id"), token, plataforma=d.get("plataforma", "android"),
            id_empresa=g.ctx["id_empresa"])
        return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": "no se pudo registrar"}), 400)
