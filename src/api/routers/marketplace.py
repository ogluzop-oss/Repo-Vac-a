"""
Router /marketplace — App Store (Fase 9 móvil, última fase): solo consulta del catálogo de plugins y
de los ya instalados. Instalar/desinstalar/actualizar/rollback son acciones de infraestructura del
escritorio (permiso `marketplace.gestionar`) — fuera de alcance del móvil, sin excepción.

A diferencia de TODOS los routers móviles anteriores, este SÍ aplica RBAC real: `marketplace.ver` y
`plugins.ver` ya protegen la misma información vía GraphQL (`api/graphql/queries.py`) y el rol OPERARIO
no los tiene por defecto (`seguridad/catalogo.py::ROLES_SISTEMA`) — exponerlo sin ese filtro sería
MENOS seguro que el propio escritorio. `requiere_auth(permiso=...)` ya soporta esto (`api/security.py`).

@deprecated (App Store retirada del menú de escritorio — decisión de producto informada: ninguna
capacidad esencial dependía de "instalar" nada aquí, ver `gui/marketplace_gui.py`): a día de hoy
`mobile_client/` NO tiene ninguna pantalla ni cliente que llame a estos endpoints (grep confirmado,
pese al "Fase 9 móvil" del párrafo anterior — nunca se llegó a construir del lado cliente) y no se ha
encontrado ningún otro consumidor real en el repo. Se conservan las rutas (no se retiran endpoints
vivos sin certeza absoluta de que nada externo dependa de ellos) pero se consideran legacy/sin uso;
no construir nada nuevo sobre ellas.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/marketplace/catalog")
    @requiere_auth(permiso="marketplace.ver")
    def marketplace_catalogo():
        from flask import g, jsonify, request
        from src.services import marketplace
        categoria = request.args.get("categoria") or None
        texto = request.args.get("q", "")
        r = marketplace.catalogo(g.ctx["id_empresa"], categoria=categoria, texto=texto)
        return jsonify(r)

    @bp.get("/marketplace/catalog/<clave>")
    @requiere_auth(permiso="marketplace.ver")
    def marketplace_detalle(clave):
        from flask import g, jsonify
        from src.services import marketplace
        r = marketplace.detalle(clave, g.ctx["id_empresa"])
        if not r:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify(r)

    @bp.get("/marketplace/installed")
    @requiere_auth(permiso="plugins.ver")
    def marketplace_instalados():
        from flask import g, jsonify
        from src.services.marketplace import movil
        r = movil.instalados(g.ctx["id_empresa"])
        return jsonify(r)
