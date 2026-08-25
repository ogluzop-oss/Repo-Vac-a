"""
Router /incidents — incidencias OPERATIVAS de tienda/almacén (roturas, limpieza, averías, etc.).
Consume `src.services.incidencias_operativas` directamente.

DISTINTO de un futuro endpoint de incidentes de SEGURIDAD (`services/seguridad/incidentes.py`, que
sigue siendo estrictamente de seguridad/administración y no se expone aquí).

`GET /incidents` devuelve, por defecto, las MÍAS (reportadas o asignadas a mí). Con `?todas=1` y el
permiso de gestión (`incidencias.gestionar`, gerencia), devuelve todas las de la empresa.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/incidents")
    @requiere_auth("incidencias.reportar")
    def incidents_listar():
        from flask import g, jsonify, request
        from src.services import incidencias_operativas as inc
        estado = request.args.get("estado")
        if request.args.get("todas") == "1":
            from src.services import autorizacion
            usuario = g.ctx["usuario"]
            es_admin = usuario.get("perfil") in ("ADMINISTRADOR", "API", "SUPERADMIN")
            if es_admin or autorizacion.puede(usuario, "incidencias.gestionar",
                                              id_empresa=g.ctx["id_empresa"]):
                return jsonify(inc.listar(estado=estado, id_empresa=g.ctx["id_empresa"]))
            return jsonify({"error": "forbidden", "permiso": "incidencias.gestionar"}), 403
        res = inc.mias(g.ctx["usuario"].get("id"), estado=estado, id_empresa=g.ctx["id_empresa"])
        return jsonify(res)

    @bp.post("/incidents")
    @requiere_auth("incidencias.reportar")
    def incidents_abrir():
        from flask import g, jsonify, request
        from src.services import incidencias_operativas as inc
        d = request.get_json(silent=True) or {}
        if not d.get("tipo") or not d.get("titulo"):
            return jsonify({"error": "tipo y titulo son obligatorios"}), 400
        iid = inc.abrir(
            d["tipo"], d["titulo"], d.get("descripcion", ""), prioridad=d.get("prioridad", "normal"),
            ubicacion=d.get("ubicacion"), reportado_por=g.ctx["usuario"].get("id"),
            id_empresa=g.ctx["id_empresa"])
        return (jsonify({"id": iid}), 201) if iid else (jsonify({"error": "no se pudo abrir"}), 400)

    @bp.post("/incidents/<int:id_incidencia>/estado")
    @requiere_auth("incidencias.reportar")
    def incidents_cambiar_estado(id_incidencia):
        from flask import g, jsonify, request
        from src.services import incidencias_operativas as inc
        d = request.get_json(silent=True) or {}
        estado = d.get("estado")
        if estado not in inc.ESTADOS:
            return jsonify({"error": "estado inválido", "validos": list(inc.ESTADOS)}), 400
        ok = inc.cambiar_estado(id_incidencia, estado, resolucion=d.get("resolucion"),
                                id_empresa=g.ctx["id_empresa"])
        return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": "no se pudo actualizar"}), 400)

    @bp.post("/incidents/<int:id_incidencia>/asignar")
    @requiere_auth("incidencias.gestionar")
    def incidents_asignar(id_incidencia):
        from flask import g, jsonify, request
        from src.services import incidencias_operativas as inc
        usuario = (request.get_json(silent=True) or {}).get("usuario")
        if not usuario:
            return jsonify({"error": "usuario es obligatorio"}), 400
        ok = inc.asignar(id_incidencia, usuario, id_empresa=g.ctx["id_empresa"])
        return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": "no se pudo asignar"}), 400)
