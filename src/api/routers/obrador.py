"""
Router /obrador — registrar un parte de producción diaria (obrador/panadería, edición Bakery) CON foto
obligatoria del lote terminado — Rediseño móvil · Grupo B, módulo 6. `registrar_produccion_diaria` es
una única llamada atómica: crea el parte Y produce cada línea (consume ingredientes por la política
única de salida de stock + suma el producto terminado por kárdex `ENTRADA_PRODUCCION`) — no hay
iniciar/finalizar como GMAO/SAT, por eso la foto es UNA por parte (`referencia=f"OBRADOR_PARTE:{id}"}`),
no por línea. Mismo patrón de dos pasos que `losses.py`/`gmao.py`/`calidad.py`/`sat.py`/`transporte.py`.

Sin permiso RBAC dedicado (no existe `obrador.*`/`produccion.*` en el catálogo) — igual que GMAO/
Transporte, exige solo autenticación.
"""

from src.api.security import requiere_auth


def _guardar_foto_parte(id_parte, id_empresa, id_usuario, file_storage):
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("obrador")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"PARTE_{id_parte}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="produccion", referencia=f"OBRADOR_PARTE:{id_parte}",
        hash_documental=h, id_empresa=id_empresa, id_tienda=None, id_usuario=id_usuario)


def registrar(bp):
    @bp.get("/obrador/parts")
    @requiere_auth()
    def obrador_listar_partes():
        from flask import g, jsonify, request
        from src.db.documentos import obtener_por_referencia
        from src.services import obrador
        eid = g.ctx["id_empresa"]
        limite = int(request.args.get("limite", 50))
        fecha = request.args.get("fecha")
        filas = obrador.listar_partes(fecha=fecha, id_empresa=eid, limite=limite)
        for f in filas:
            doc = obtener_por_referencia(f"OBRADOR_PARTE:{f['id']}", id_empresa=eid)
            f["id_documento_foto"] = doc["id_documento"] if doc else None
        return jsonify(filas)

    @bp.post("/obrador/parts")
    @requiere_auth()
    def obrador_registrar_parte():
        import json

        from flask import g, jsonify, request
        from src.services import obrador
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Foto del lote terminado obligatoria"}), 400
        d = request.form
        try:
            items = json.loads(d.get("items") or "[]")
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Líneas de producción inválidas"}), 400
        if not items:
            return jsonify({"ok": False, "error": "Añade al menos una línea de producción"}), 400
        eid = g.ctx["id_empresa"]
        r = obrador.registrar_produccion_diaria(
            items, turno=d.get("turno"), responsable=d.get("responsable"), id_empresa=eid,
            usuario=g.ctx["usuario"].get("nombre"))
        if not r.get("ok"):
            return jsonify(r), 400
        id_doc = _guardar_foto_parte(r["parte"], eid, g.ctx["usuario"].get("id"), foto)
        if not id_doc:
            return jsonify({"ok": False, "error": "No se pudo guardar la foto"}), 400
        r["id_documento"] = id_doc
        return jsonify(r), 201

    @bp.get("/obrador/photo/<id_documento>")
    @requiere_auth()
    def obrador_foto_parte(id_documento):
        import os

        from flask import g, send_file
        from src.db.documentos import obtener_documento
        doc = obtener_documento(id_documento)
        if (not doc or doc.get("id_empresa") != g.ctx["id_empresa"]
                or doc.get("tipo_documento") != "produccion"):
            return {"error": "No encontrado"}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.exists(ruta):
            return {"error": "No encontrado"}, 404
        return send_file(ruta)
