"""
Router /transporte — mis rutas de reparto asignadas, iniciar, entregar una parada CON foto obligatoria,
reportar una incidencia (cliente ausente/rechazo/dirección incorrecta) y cerrar la ruta — Rediseño móvil
· Grupo B, módulo 5. `transporte.entregar_parada` ya es idempotente y usa la política única de salida de
stock (kárdex `SALIDA_REPARTO`) — se invoca tal cual. Sin pad de firma: `transporte_paradas` no tiene
ninguna columna de conformidad/firma y no existe ningún momento de doble parte (ver contexto del plan).

Mismo patrón de dos pasos que `losses.py`/`gmao.py`/`calidad.py`/`sat.py` para la foto (bytes a disco +
hash + `db.documentos.registrar_documento`), enlazada POR PARADA (`referencia=f"PARADA:{id}"`).

Sin permiso RBAC dedicado todavía (no existe `transporte.*`/`reparto.*` en el catálogo) — igual que
GMAO, exige solo autenticación.
"""

from src.api.security import requiere_auth

_ESTADOS_ABIERTOS_EXCLUIDOS = ("cerrada",)


def _guardar_foto_parada(id_parada, id_empresa, id_usuario, file_storage):
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("transporte")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"PARADA_{id_parada}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="reparto", referencia=f"PARADA:{id_parada}",
        hash_documental=h, id_empresa=id_empresa, id_tienda=None, id_usuario=id_usuario)


def registrar(bp):
    @bp.get("/transporte/routes")
    @requiere_auth()
    def transporte_mis_rutas():
        from flask import g, jsonify
        from src.services import transporte
        eid = g.ctx["id_empresa"]
        todas = transporte.listar_rutas(id_empresa=eid, id_conductor=g.ctx["usuario"].get("id"))
        abiertas = [r for r in todas if r.get("estado") not in _ESTADOS_ABIERTOS_EXCLUIDOS]
        return jsonify(abiertas)

    @bp.get("/transporte/routes/<int:id_ruta>")
    @requiere_auth()
    def transporte_obtener_ruta(id_ruta):
        from flask import g, jsonify
        from src.services import transporte
        ruta = transporte.obtener_ruta(id_ruta, id_empresa=g.ctx["id_empresa"])
        # JWT "sub" siempre llega como string; id_conductor es INT en BD — comparar como texto para
        # no fallar por tipo (a diferencia del filtro SQL de listar_rutas, que sí coacciona el tipo).
        if not ruta or str(ruta.get("id_conductor")) != str(g.ctx["usuario"].get("id")):
            return jsonify({"error": "No encontrada"}), 404
        return jsonify(ruta)

    @bp.post("/transporte/routes/<int:id_ruta>/start")
    @requiere_auth()
    def transporte_iniciar_ruta(id_ruta):
        from flask import g, jsonify
        from src.services import transporte
        ok = transporte.iniciar_ruta(id_ruta, id_empresa=g.ctx["id_empresa"])
        return jsonify({"ok": ok}), (200 if ok else 400)

    @bp.post("/transporte/stops/<int:id_parada>/deliver")
    @requiere_auth()
    def transporte_entregar_parada(id_parada):
        from flask import g, jsonify, request
        from src.services import transporte
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Foto de la entrega obligatoria"}), 400
        eid = g.ctx["id_empresa"]
        id_doc = _guardar_foto_parada(id_parada, eid, g.ctx["usuario"].get("id"), foto)
        if not id_doc:
            return jsonify({"ok": False, "error": "No se pudo guardar la foto"}), 400
        r = transporte.entregar_parada(id_parada, id_empresa=eid,
                                       usuario=g.ctx["usuario"].get("nombre"))
        r["id_documento"] = id_doc
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/transporte/stops/<int:id_parada>/incident")
    @requiere_auth()
    def transporte_reportar_incidencia(id_parada):
        from flask import g, jsonify, request
        from src.services import transporte
        datos = request.form if request.files else (request.get_json(silent=True) or {})
        eid = g.ctx["id_empresa"]
        r = transporte.reportar_incidencia(id_parada, datos.get("motivo"), id_empresa=eid,
                                           usuario=g.ctx["usuario"].get("nombre"))
        if not r.get("ok"):
            return jsonify(r), 400
        foto = request.files.get("foto") if request.files else None
        if foto and foto.filename:
            id_doc = _guardar_foto_parada(id_parada, eid, g.ctx["usuario"].get("id"), foto)
            if id_doc:
                r["id_documento"] = id_doc
        return jsonify(r), 200

    @bp.post("/transporte/routes/<int:id_ruta>/close")
    @requiere_auth()
    def transporte_cerrar_ruta(id_ruta):
        from flask import g, jsonify
        from src.services import transporte
        r = transporte.cerrar_ruta(id_ruta, id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/transporte/stops/photo/<id_documento>")
    @requiere_auth()
    def transporte_foto_parada(id_documento):
        import os

        from flask import g, send_file
        from src.db.documentos import obtener_documento
        doc = obtener_documento(id_documento)
        if (not doc or doc.get("id_empresa") != g.ctx["id_empresa"]
                or doc.get("tipo_documento") != "reparto"):
            return {"error": "No encontrado"}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.exists(ruta):
            return {"error": "No encontrado"}, 404
        return send_file(ruta)
