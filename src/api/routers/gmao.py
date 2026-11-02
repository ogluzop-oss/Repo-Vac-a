"""
Router /gmao — localizar un activo escaneando su QR y ejecutar in situ el ciclo de su OT (iniciar,
consultar repuestos pendientes, finalizar con foto de la reparación) — Rediseño móvil · Grupo B,
módulo 2. Las OTs se siguen creando/planificando desde escritorio (`gui/gmao_dashboard.py`); esto solo
mueve la EJECUCIÓN física al móvil. Consume `src.services.gmao.activos`/`ordenes` (motor completo, sin
lógica nueva) + `src.db.documentos` para la foto de evidencia — mismo patrón de dos pasos (escribir
bytes + hash + `registrar_documento`, luego enlazar) ya usado en `losses.py`, aquí enlazando además con
`activos.adjuntar_documento` (existía sin llamador).

`POST /gmao/orders/<id>/finish` exige `multipart/form-data` con un campo `foto` — a diferencia de
Mermas, aquí la foto SIEMPRE es obligatoria (evidencia de la reparación antes de cerrar la OT).

Sin permiso RBAC dedicado todavía (no existe catálogo `gmao.*` en `seguridad/catalogo.py` para
end-users móviles): exige solo autenticación, igual que `/losses`/`/location`/`/articles`.
"""

from src.api.security import requiere_auth

_ESTADOS_ABIERTOS_EXCLUIDOS = ("finalizada", "cancelada")


def _guardar_foto_ot(oid, id_empresa, id_usuario, file_storage):
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("gmao")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"OT_{oid}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="mantenimiento", referencia=f"OT:{oid}",
        hash_documental=h, id_empresa=id_empresa, id_tienda=None, id_usuario=id_usuario)


def registrar(bp):
    @bp.get("/gmao/assets/by-code")
    @requiere_auth()
    def gmao_activo_por_codigo():
        from flask import g, jsonify, request
        from src.services.gmao import activos
        codigo = (request.args.get("codigo") or "").strip()
        if not codigo:
            return jsonify({"error": "codigo requerido"}), 400
        activo = activos.buscar_por_codigo(codigo, id_empresa=g.ctx["id_empresa"])
        if not activo:
            return jsonify({"error": "Activo no encontrado"}), 404
        return jsonify(activo)

    @bp.get("/gmao/assets/<int:id_activo>/orders")
    @requiere_auth()
    def gmao_ordenes_de_activo(id_activo):
        from flask import g, jsonify
        from src.services.gmao import ordenes
        todas = ordenes.listar(id_activo=id_activo, id_empresa=g.ctx["id_empresa"])
        abiertas = [o for o in todas if o.get("estado") not in _ESTADOS_ABIERTOS_EXCLUIDOS]
        return jsonify(abiertas)

    @bp.post("/gmao/orders/<int:oid>/start")
    @requiere_auth()
    def gmao_iniciar_orden(oid):
        from flask import g, jsonify
        from src.services.gmao import ordenes
        r = ordenes.iniciar(oid, tecnico=g.ctx["usuario"].get("id"), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/gmao/orders/<int:oid>/parts")
    @requiere_auth()
    def gmao_repuestos_de_orden(oid):
        from flask import g, jsonify
        from src.services.gmao import ordenes
        return jsonify(ordenes.listar_repuestos(oid, id_empresa=g.ctx["id_empresa"]))

    @bp.post("/gmao/orders/<int:oid>/finish")
    @requiere_auth()
    def gmao_finalizar_orden(oid):
        from flask import g, jsonify, request
        from src.services.gmao import activos, ordenes
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Foto de la reparación obligatoria"}), 400
        id_empresa = g.ctx["id_empresa"]
        id_doc = _guardar_foto_ot(oid, id_empresa, g.ctx["usuario"].get("id"), foto)
        if not id_doc:
            return jsonify({"ok": False, "error": "No se pudo guardar la foto"}), 400
        ot = ordenes.obtener(oid)
        if ot and ot.get("id_activo"):
            activos.adjuntar_documento(ot["id_activo"], f"Reparación OT {oid}",
                                       id_documento=id_doc, id_empresa=id_empresa)
        r = ordenes.finalizar(oid, id_empresa=id_empresa, usuario=g.ctx["usuario"].get("id"))
        r["id_documento"] = id_doc
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/gmao/orders/photo/<id_documento>")
    @requiere_auth()
    def gmao_foto_orden(id_documento):
        import os

        from flask import g, send_file
        from src.db.documentos import obtener_documento
        doc = obtener_documento(id_documento)
        if (not doc or doc.get("id_empresa") != g.ctx["id_empresa"]
                or doc.get("tipo_documento") != "mantenimiento"):
            return {"error": "No encontrado"}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.exists(ruta):
            return {"error": "No encontrado"}, 404
        return send_file(ruta)
