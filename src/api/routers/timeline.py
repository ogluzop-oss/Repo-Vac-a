"""
Router /timeline — cronología unificada de comunicaciones (salientes de cualquier canal + correos
entrantes) por contacto. Consume `src.services.ccp.timeline` directamente: ya es la capa de servicio
real (Communication Timeline, CCP Fase II · B4).

Sin permiso RBAC dedicado, igual que el historial de `/communications` (mismo dominio CCP).
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/timeline")
    @requiere_auth()
    def timeline_ver():
        from flask import g, jsonify, request
        from src.services.ccp import timeline as tl
        correo = request.args.get("correo")
        limite = int(request.args.get("limite", 200))
        if request.args.get("agrupado") == "1":
            return jsonify(tl.timeline_agrupado(g.ctx["id_empresa"], correo=correo, limite=limite))
        return jsonify(tl.timeline(g.ctx["id_empresa"], correo=correo, limite=limite))
