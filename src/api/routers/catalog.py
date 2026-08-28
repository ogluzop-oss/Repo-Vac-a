"""
Router /catalogo — catálogo de productos (solo lectura). Consume `src.services.catalogo.service`
directamente (ya era la capa de servicio real).

Portado desde el blueprint legacy `src/backend/api.py` (Fase A1, ahora sustituido por esta API —
ver ADR-0001) al fusionar los dos backends `/api/v1` que coexistían sin que ninguno lo supiera: uno
quedó documentado como "oficial" pero nunca se montó en el servidor real que usan la app móvil y
`wsgi.py`. Mismo comportamiento que el original: la vista (pública/operativa, con o sin productos
ocultos) depende del rol del usuario.
"""

from src.api.security import requiere_auth

_CLAVES_SECRETAS = ("password", "passwd", "api_key", "api_secret", "webhook_secret",
                    "refresh_hash", "access_token", "refresh_token", "secret", "token",
                    "clave", "hash")


def _sin_secretos(obj):
    """Elimina recursivamente claves que parezcan secretas (defensa en profundidad)."""
    if isinstance(obj, dict):
        return {k: _sin_secretos(v) for k, v in obj.items()
                if not any(s in str(k).lower() for s in _CLAVES_SECRETAS)}
    if isinstance(obj, list):
        return [_sin_secretos(x) for x in obj]
    return obj


def registrar(bp):
    @bp.get("/catalogo/productos")
    @requiere_auth("ventas.ver")
    def catalogo_productos():
        from flask import g, jsonify, request
        from src.services.catalogo import service as C
        interno = C.es_vista_interna(g.ctx["usuario"].get("perfil"))
        a = request.args
        prods = C.listar_productos(interno=interno, categoria=a.get("categoria", type=int),
                                   marca=a.get("marca", type=int), texto=a.get("texto"),
                                   id_empresa=g.ctx["id_empresa"],
                                   limite=a.get("limite", default=200, type=int))
        return jsonify(_sin_secretos({"productos": prods, "total": len(prods)}))

    @bp.get("/catalogo/productos/<int:pid>")
    @requiere_auth("ventas.ver")
    def catalogo_producto(pid):
        from flask import g, jsonify
        from src.services.catalogo import service as C
        p = C.producto(id_producto=pid, interno=C.es_vista_interna(g.ctx["usuario"].get("perfil")),
                       id_empresa=g.ctx["id_empresa"])
        if not p:
            return jsonify({"error": "producto no encontrado"}), 404
        return jsonify(_sin_secretos(p))

    @bp.get("/catalogo/categorias")
    @requiere_auth("ventas.ver")
    def catalogo_categorias():
        from flask import g, jsonify
        from src.services.catalogo import service as C
        return jsonify({"categorias": C.listar_categorias(arbol=True, solo_visibles=False,
                                                           id_empresa=g.ctx["id_empresa"])})
