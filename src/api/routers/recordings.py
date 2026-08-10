"""
Router /recordings (Videovigilancia · acceso remoto) — reutiliza la seguridad Fase III (JWT+tenant+RBAC).

Un usuario normal solo accede a las grabaciones de SU empresa; el perfil SUPERADMIN puede cruzar
departamentos/empresas (acceso multi-sede autorizado). Consume `src.services.camaras`. Solo lectura.
"""

from src.api.security import requiere_auth


def _es_super(ctx):
    return str((ctx.get("usuario") or {}).get("perfil", "")).upper() == "SUPERADMIN"


def registrar(bp):
    @bp.get("/recordings")
    @requiere_auth()
    def recording_meta():
        from flask import g, jsonify, request
        from src.services import camaras
        cam = request.args.get("camara"); fecha = request.args.get("fecha")
        if not cam or not fecha:
            return jsonify({"error": "camara y fecha requeridos"}), 400
        grab = camaras.grabacion_de(int(cam), fecha, id_empresa=g.ctx["id_empresa"],
                                    permitir_super=_es_super(g.ctx))
        return (jsonify(grab), 200) if grab else (jsonify({"error": "no encontrada"}), 404)

    @bp.get("/recordings/dates")
    @requiere_auth()
    def recording_dates():
        from flask import g, jsonify, request
        from src.services import camaras
        cam = request.args.get("camara")
        if not cam:
            return jsonify({"error": "camara requerida"}), 400
        return jsonify(camaras.fechas_disponibles(int(cam), id_empresa=g.ctx["id_empresa"],
                                                  permitir_super=_es_super(g.ctx)))

    @bp.get("/recordings/download")
    @requiere_auth()
    def recording_download():
        from flask import g, jsonify, request, send_file
        from src.services import camaras
        cam = request.args.get("camara"); fecha = request.args.get("fecha")
        grab = camaras.grabacion_de(int(cam), fecha, id_empresa=g.ctx["id_empresa"],
                                    permitir_super=_es_super(g.ctx)) if cam and fecha else None
        if not grab or not grab.get("ruta"):
            return jsonify({"error": "no encontrada"}), 404
        import os
        if not os.path.exists(grab["ruta"]):
            return jsonify({"error": "fichero no disponible"}), 404
        return send_file(grab["ruta"], as_attachment=True)
