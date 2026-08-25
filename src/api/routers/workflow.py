"""
Router /workflow — bandeja de aprobaciones del usuario autenticado. Consume
`src.services.workflow.workflow_engine` directamente (motor BPM/aprobaciones ya existente).

Sin permiso RBAC dedicado: `tareas_para_usuario` ya filtra por autorización POR TAREA (rol/permiso/
usuario asignado/delegación vía `_actor_autorizado`), igual que la propia bandeja de escritorio — no
hace falta un permiso adicional para "ver mi bandeja".
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/workflow/tasks")
    @requiere_auth()
    def workflow_bandeja():
        from flask import g, jsonify, request
        from src.services.workflow import workflow_engine as wf
        estado = request.args.get("estado", "PENDIENTE")
        res = wf.tareas_para_usuario(g.ctx["usuario"], estado=estado, id_empresa=g.ctx["id_empresa"])
        return jsonify(res)

    @bp.post("/workflow/tasks/<int:id_tarea>/aprobar")
    @requiere_auth()
    def workflow_aprobar(id_tarea):
        from flask import g, jsonify, request
        from src.services.workflow import workflow_engine as wf
        comentario = (request.get_json(silent=True) or {}).get("comentario")
        try:
            res = wf.aprobar_tarea(id_tarea, actor=g.ctx["usuario"], comentario=comentario,
                                   id_empresa=g.ctx["id_empresa"])
            return jsonify(res)
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except wf.ErrorWorkflow as e:
            return jsonify({"error": str(e)}), 400

    @bp.post("/workflow/tasks/<int:id_tarea>/rechazar")
    @requiere_auth()
    def workflow_rechazar(id_tarea):
        from flask import g, jsonify, request
        from src.services.workflow import workflow_engine as wf
        comentario = (request.get_json(silent=True) or {}).get("comentario")
        try:
            res = wf.rechazar_tarea(id_tarea, actor=g.ctx["usuario"], comentario=comentario,
                                    id_empresa=g.ctx["id_empresa"])
            return jsonify(res)
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except wf.ErrorWorkflow as e:
            return jsonify({"error": str(e)}), 400
