"""
Portal Web · Rutas REST (Fase WEB-04). Se montan en el blueprint API existente (`/api/v1/portal/*`) — NO es un
backend paralelo. Reutiliza `api.security.requiere_auth` (JWT + RBAC + tenant del token). NO duplica las APIs
de negocio: expone el DESCRIPTOR del módulo y la NAVEGACIÓN filtrada por permisos; los datos reales se sirven
por los routers/servicios ya existentes. Preparado; sin lógica de negocio nueva.
"""


def registrar(bp):
    from flask import g, jsonify

    from src.api.security import requiere_auth

    @bp.get("/portal/live")
    def _portal_live():
        # Público: sólo indica que el módulo está montado (no expone datos).
        return jsonify({"portal": "back_office", "status": "preparado"})

    @bp.get("/portal/descriptor")
    def _portal_descriptor():
        from src.portal_web import navegacion
        return jsonify(navegacion.descriptor())

    @bp.get("/portal/navegacion")
    @requiere_auth()            # JWT obligatorio; tenant del token; RBAC/entitlements aplicados en acceso
    def _portal_navegacion():
        from src.portal_web import layout
        ctx = g.ctx
        return jsonify(layout.layout(usuario=ctx.get("usuario"), id_empresa=ctx.get("id_empresa"),
                                     id_tienda=(ctx.get("usuario") or {}).get("id_tienda")))
