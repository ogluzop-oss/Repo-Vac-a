"""
Router /calidad — registrar una inspección de calidad (recepción/producción/final) CON foto obligatoria
del artículo/lote inspeccionado — Rediseño móvil · Grupo B, módulo 3. `inspecciones.registrar_inspeccion`
es una inserción única (sin máquina de estados, a diferencia de la OT de GMAO) que YA abre una No
Conformidad sola cuando `resultado="rechazada"` — se hereda ese comportamiento sin tocarlo. La foto se
enlaza con el mismo patrón de dos pasos (bytes a disco + hash + `db.documentos.registrar_documento`) ya
usado en `losses.py`/`gmao.py`, con `referencia=f"INSPECCION:{id}"`.

A diferencia de Mermas/GMAO (sin permiso RBAC dedicado todavía), Calidad YA tiene `inspecciones.crear`
en el catálogo (`services/seguridad/catalogo.py`) — se aplica en el POST vía `requiere_auth(permiso)`
(mismo patrón que `routers/incidents.py`).
"""

from src.api.security import requiere_auth


def _guardar_foto_inspeccion(iid, id_empresa, id_usuario, file_storage):
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("calidad")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"INSPECCION_{iid}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="inspeccion", referencia=f"INSPECCION:{iid}",
        hash_documental=h, id_empresa=id_empresa, id_tienda=None, id_usuario=id_usuario)


def registrar(bp):
    @bp.get("/calidad/inspections")
    @requiere_auth()
    def calidad_listar():
        from flask import g, jsonify, request
        from src.db.documentos import obtener_por_referencia
        from src.services.calidad import inspecciones
        limite = int(request.args.get("limite", 50))
        eid = g.ctx["id_empresa"]
        filas = inspecciones.listar(id_empresa=eid, limite=limite)
        for f in filas:
            doc = obtener_por_referencia(f"INSPECCION:{f['id']}", id_empresa=eid)
            f["id_documento_foto"] = doc["id_documento"] if doc else None
        return jsonify(filas)

    @bp.post("/calidad/inspections")
    @requiere_auth("inspecciones.crear")
    def calidad_registrar():
        from flask import g, jsonify, request
        from src.services.calidad import inspecciones
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Foto del artículo/lote inspeccionado obligatoria"}), 400
        d = request.form
        try:
            cant_insp = float(d.get("cantidad_inspeccionada") or 0)
            cant_rech = float(d.get("cantidad_rechazada") or 0)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Cantidad inválida"}), 400
        eid = g.ctx["id_empresa"]
        try:
            r = inspecciones.registrar_inspeccion(
                fase=d.get("fase") or "recepcion", articulo=d.get("articulo"),
                cantidad_inspeccionada=cant_insp, cantidad_rechazada=cant_rech,
                resultado=d.get("resultado") or "aceptada", observaciones=d.get("observaciones"),
                inspector=g.ctx["usuario"].get("id"), id_empresa=eid)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        if not r.get("ok"):
            return jsonify(r), 400
        id_doc = _guardar_foto_inspeccion(r["inspeccion"], eid, g.ctx["usuario"].get("id"), foto)
        if not id_doc:
            return jsonify({"ok": False, "error": "No se pudo guardar la foto"}), 400
        r["id_documento"] = id_doc
        return jsonify(r), 201

    @bp.get("/calidad/photo/<id_documento>")
    @requiere_auth()
    def calidad_foto(id_documento):
        import os

        from flask import g, send_file
        from src.db.documentos import obtener_documento
        doc = obtener_documento(id_documento)
        if (not doc or doc.get("id_empresa") != g.ctx["id_empresa"]
                or doc.get("tipo_documento") != "inspeccion"):
            return {"error": "No encontrado"}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.exists(ruta):
            return {"error": "No encontrado"}, 404
        return send_file(ruta)
