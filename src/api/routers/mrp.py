"""
Router /mrp — mis órdenes de fabricación (OF) abiertas, iniciar/pausar, consumir materiales previstos,
registrar producción CON foto obligatoria (repetible, una foto por lote producido) y finalizar —
Rediseño móvil · Grupo B, módulo 7 (último). `registrar_produccion` es repetible (cada llamada añade
una fila a `of_produccion`), por eso la foto se enlaza POR PRODUCCIÓN (`referencia=f"OFPROD:{id}"`), no
por OF — mismo criterio que SAT enlaza por intervención, no por ticket. `consumir_materiales` no lleva
foto: no hay ningún dato de operario ni artefacto fotografiable en ese instante (ver docstring del
propio servicio). Mismo patrón de dos pasos que `losses.py`/`gmao.py`/`calidad.py`/`sat.py`/
`transporte.py`/`obrador.py` para la foto, reutilizando el tipo documental `"produccion"` (ya usado por
Obrador — ambos son evidencia de producción, se distinguen por la `referencia`).

A diferencia de GMAO/Transporte/Obrador (sin RBAC dedicado), MRP SÍ tiene permisos reales ya cableados
en escritorio (`mrp_dashboard.py` gatea todas estas acciones tras `mrp.admin`, sin granularidad por
acción) — se aplica el mismo permiso aquí, igual que Calidad/SAT reutilizan los suyos.
"""

from src.api.security import requiere_auth

_ESTADOS_ACCIONABLES = ("liberada", "en_curso", "pausada")


def _guardar_foto_produccion(id_produccion, id_empresa, id_usuario, file_storage):
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("mrp")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"OFPROD_{id_produccion}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="produccion", referencia=f"OFPROD:{id_produccion}",
        hash_documental=h, id_empresa=id_empresa, id_tienda=None, id_usuario=id_usuario)


def registrar(bp):
    @bp.get("/mrp/orders")
    @requiere_auth()
    def mrp_listar_ordenes():
        from flask import g, jsonify
        from src.services.mrp import ordenes
        todas = ordenes.listar(id_empresa=g.ctx["id_empresa"])
        accionables = [o for o in todas if o.get("estado") in _ESTADOS_ACCIONABLES]
        return jsonify(accionables)

    @bp.get("/mrp/orders/<int:oid>")
    @requiere_auth()
    def mrp_obtener_orden(oid):
        from flask import g, jsonify
        from src.services.mrp import ordenes
        of = ordenes.obtener_of(oid)
        if not of or of.get("id_empresa") != g.ctx["id_empresa"]:
            return jsonify({"error": "No encontrada"}), 404
        return jsonify(of)

    @bp.post("/mrp/orders/<int:oid>/start")
    @requiere_auth("mrp.admin")
    def mrp_iniciar_orden(oid):
        from flask import g, jsonify
        from src.services.mrp import ordenes
        try:
            r = ordenes.iniciar(oid, id_empresa=g.ctx["id_empresa"])
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/mrp/orders/<int:oid>/pause")
    @requiere_auth("mrp.admin")
    def mrp_pausar_orden(oid):
        from flask import g, jsonify
        from src.services.mrp import ordenes
        try:
            r = ordenes.pausar(oid, id_empresa=g.ctx["id_empresa"])
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/mrp/orders/<int:oid>/consumptions")
    @requiere_auth()
    def mrp_listar_consumos(oid):
        from flask import g, jsonify
        from src.services.mrp import ordenes
        return jsonify(ordenes.listar_consumos(oid, id_empresa=g.ctx["id_empresa"]))

    @bp.post("/mrp/orders/<int:oid>/consume")
    @requiere_auth("mrp.admin")
    def mrp_consumir_materiales(oid):
        from flask import g, jsonify
        from src.services.mrp import ordenes
        r = ordenes.consumir_materiales(oid, id_empresa=g.ctx["id_empresa"],
                                        usuario=g.ctx["usuario"].get("nombre"))
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/mrp/orders/<int:oid>/productions")
    @requiere_auth()
    def mrp_listar_producciones(oid):
        from flask import g, jsonify
        from src.db.documentos import obtener_por_referencia
        from src.services.mrp import ordenes
        eid = g.ctx["id_empresa"]
        filas = ordenes.listar_producciones(oid, id_empresa=eid)
        for f in filas:
            doc = obtener_por_referencia(f"OFPROD:{f['id']}", id_empresa=eid)
            f["id_documento_foto"] = doc["id_documento"] if doc else None
        return jsonify(filas)

    @bp.post("/mrp/orders/<int:oid>/produce")
    @requiere_auth("mrp.admin")
    def mrp_registrar_produccion(oid):
        from flask import g, jsonify, request
        from src.services.mrp import ordenes
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Foto del lote producido obligatoria"}), 400
        try:
            cantidad = float(request.form.get("cantidad") or 0)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Cantidad inválida"}), 400
        if cantidad <= 0:
            return jsonify({"ok": False, "error": "La cantidad debe ser mayor que 0"}), 400
        eid = g.ctx["id_empresa"]
        r = ordenes.registrar_produccion(oid, cantidad, id_empresa=eid,
                                         usuario=g.ctx["usuario"].get("nombre"))
        if not r.get("ok"):
            return jsonify(r), 400
        id_doc = _guardar_foto_produccion(r["id_produccion"], eid, g.ctx["usuario"].get("id"), foto)
        if not id_doc:
            return jsonify({"ok": False, "error": "No se pudo guardar la foto"}), 400
        r["id_documento"] = id_doc
        return jsonify(r), 201

    @bp.post("/mrp/orders/<int:oid>/finish")
    @requiere_auth("mrp.admin")
    def mrp_finalizar_orden(oid):
        from flask import g, jsonify
        from src.services.mrp import ordenes
        r = ordenes.finalizar(oid, id_empresa=g.ctx["id_empresa"], usuario=g.ctx["usuario"].get("nombre"))
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/mrp/orders/photo/<id_documento>")
    @requiere_auth()
    def mrp_foto_produccion(id_documento):
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
