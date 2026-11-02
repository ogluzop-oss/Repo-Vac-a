"""
Router /location — ubicación física de artículos en tienda/almacén, y (Ajuste post-lanzamiento ·
Módulo 3) el plano interior + cálculo de rutas. Consume `src.services.ubicacion`, que a su vez delega
en `db.ubicaciones` (el mismo motor que usa `gui/ubicacion_tienda.py`) — no se reimplementa ningún
criterio de asignación ni de cálculo de ruta.

"GPS interno" en móvil es una consulta + ruta calculada localmente (A*, extraído de la GUI de
escritorio a `services.ubicacion.pathfinding`, sin dependencias de Qt) — nunca posicionamiento en
tiempo real (el escritorio tampoco lo usa: ver el plan para el detalle).

Sin permiso RBAC dedicado todavía (no existe `ubicacion.ver`/`ubicacion.editar` en el catálogo):
exige solo autenticación, igual que `/orders`.
"""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/location")
    @requiere_auth()
    def location_buscar():
        from flask import g, jsonify, request
        from src.services import ubicacion
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 50))
        res = ubicacion.buscar(g.ctx["id_empresa"], request.args.get("q", ""), limite=limite)
        return jsonify(envolver(res, p))

    @bp.post("/location/assign")
    @requiere_auth()
    def location_asignar():
        from flask import g, jsonify, request
        from src.services import ubicacion
        d = request.get_json(silent=True) or {}
        r = ubicacion.asignar(g.ctx["id_empresa"], d.get("codigo"), d.get("pasillo"),
                              d.get("estanteria"), d.get("nivel"), d.get("tipo"))
        return (jsonify(r), 200) if r.get("ok") else (jsonify(r), 400)

    @bp.get("/location/map")
    @requiere_auth()
    def location_mapa():
        from flask import jsonify, request
        from src.services import ubicacion
        planta = request.args.get("planta", type=int)
        info = ubicacion.mapa_info(planta)
        if not info:
            return jsonify({"error": "No hay ningún plano cargado."}), 404
        return jsonify(info)

    @bp.get("/location/map/image")
    @requiere_auth()
    def location_mapa_imagen():
        from flask import request, send_file
        from src.services import ubicacion
        planta = request.args.get("planta", type=int)
        if planta is None:
            info = ubicacion.mapa_info(None)
            if not info:
                return {"error": "No hay ningún plano cargado."}, 404
            planta = info["planta_index"]
        ruta = ubicacion.imagen_absoluta(planta)
        if not ruta:
            return {"error": "No hay imagen de plano disponible."}, 404
        return send_file(ruta)

    @bp.get("/location/map/coords")
    @requiere_auth()
    def location_mapa_coords():
        from flask import jsonify, request
        from src.services import ubicacion
        codigo = request.args.get("codigo") or ""
        coords = ubicacion.coords_articulo(codigo)
        if not coords:
            return jsonify({"error": "Sin coordenadas para este artículo."}), 404
        return jsonify(coords)

    @bp.post("/location/map/route")
    @requiere_auth()
    def location_mapa_ruta():
        from flask import jsonify, request
        from src.services import ubicacion
        d = request.get_json(silent=True) or {}
        planta = d.get("planta")
        r = ubicacion.calcular_ruta(planta, d.get("origen") or {}, d.get("destino") or {})
        return (jsonify(r), 200) if r.get("ok") else (jsonify(r), 400)
