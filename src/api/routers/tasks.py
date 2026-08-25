"""
Router /tasks — tareas empresariales (asignación/seguimiento). Consume `src.services.tareas`
directamente: ya es la capa de servicio real, no hace falta una capa fina adicional.

Alcance de esta primera iteración: listar MIS tareas asignadas, crear una tarea y cambiar su estado.
Los comentarios (`tareas.comentar`) quedan para una iteración posterior si se necesitan en el móvil.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/tasks")
    @requiere_auth("tareas.gestionar")
    def tasks_listar():
        from flask import g, jsonify, request
        from src.services import tareas
        res = tareas.tareas_de(g.ctx["usuario"].get("id"), estado=request.args.get("estado"),
                               id_empresa=g.ctx["id_empresa"])
        return jsonify(res)

    @bp.post("/tasks")
    @requiere_auth("tareas.gestionar")
    def tasks_crear():
        from flask import g, jsonify, request
        from src.services import tareas
        d = request.get_json(silent=True) or {}
        if not d.get("titulo"):
            return jsonify({"error": "titulo es obligatorio"}), 400
        # Sin destinatario explícito, la tarea se autoasigna el propio usuario.
        asignado_a = d.get("asignado_a") or g.ctx["usuario"].get("id")
        tid = tareas.crear_tarea(
            d["titulo"], descripcion=d.get("descripcion"), asignado_a=asignado_a,
            creado_por=g.ctx["usuario"].get("id"), prioridad=d.get("prioridad", "normal"),
            vencimiento=d.get("vencimiento"), id_empresa=g.ctx["id_empresa"])
        return (jsonify({"id": tid}), 201) if tid else (jsonify({"error": "no se pudo crear"}), 400)

    @bp.post("/tasks/<int:id_tarea>/estado")
    @requiere_auth("tareas.gestionar")
    def tasks_cambiar_estado(id_tarea):
        from flask import g, jsonify, request
        from src.services import tareas
        estado = (request.get_json(silent=True) or {}).get("estado")
        if estado not in tareas.ESTADOS:
            return jsonify({"error": "estado inválido", "validos": list(tareas.ESTADOS)}), 400
        ok = tareas.cambiar_estado(id_tarea, estado, id_empresa=g.ctx["id_empresa"])
        return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": "no se pudo actualizar"}), 400)
