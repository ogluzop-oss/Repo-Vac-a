"""
Router /losses — registro y consulta de mermas, con foto de evidencia opcional (Rediseño móvil ·
Grupo B, módulo 1): fotografiar el producto dañado/caducado en el momento, en vez de solo teclear un
formulario desde la oficina (que es lo que hacía la pantalla móvil de Mermas retirada en el Grupo A).
Consume `src.services.mermas` (motor completo, sin cambios) + `src.db.documentos` (centro documental
compartido) para la foto — mismo patrón (escribir bytes a disco + hash + registrar) que
`services.fiscal.evidencias.guardar_evidencia`, sin inventar uno nuevo.

`POST /losses` acepta `multipart/form-data` (con un campo `foto` opcional) o JSON, por compatibilidad
— es el primer endpoint de la API que acepta subida de fichero. No se ha construido un endpoint
genérico de "evidencia": cada módulo del Grupo B expondrá su propio campo de fichero cuando le toque.

Sin permiso RBAC dedicado todavía (no existe `mermas.registrar` en el catálogo de
`seguridad/catalogo.py`): exige solo autenticación, igual que `/location`/`/articles`/`/orders`.
"""

from src.api.security import requiere_auth


def _guardar_foto_merma(id_merma, id_empresa, id_usuario, file_storage):
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("mermas")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"MERMA_{id_merma}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="merma", referencia=f"MERMA:{id_merma}",
        hash_documental=h, id_empresa=id_empresa, id_tienda=None, id_usuario=id_usuario)


def registrar(bp):
    @bp.get("/losses")
    @requiere_auth()
    def losses_listar():
        from flask import g, jsonify, request
        from src.services import mermas
        limite = int(request.args.get("limite", 50))
        res = mermas.listar(g.ctx["id_empresa"], limite=limite)
        return jsonify(res)

    @bp.post("/losses")
    @requiere_auth()
    def losses_registrar():
        from flask import g, jsonify, request
        from src.services import mermas
        datos = request.form if request.files else (request.get_json(silent=True) or {})
        r = mermas.registrar(
            g.ctx["id_empresa"], g.ctx["usuario"].get("id_tienda"),
            datos.get("codigo"), datos.get("cantidad"), datos.get("motivo"), datos.get("origen"))
        if not r.get("ok"):
            return jsonify(r), 400
        foto = request.files.get("foto") if request.files else None
        if foto and foto.filename:
            try:
                id_doc = _guardar_foto_merma(
                    r["id"], g.ctx["id_empresa"], g.ctx["usuario"].get("id"), foto)
                if id_doc:
                    r["id_documento"] = id_doc
            except Exception:
                pass
        return jsonify(r), 201

    @bp.get("/losses/photo/<id_documento>")
    @requiere_auth()
    def losses_foto(id_documento):
        import os

        from flask import g, send_file
        from src.db.documentos import obtener_documento
        doc = obtener_documento(id_documento)
        if (not doc or doc.get("id_empresa") != g.ctx["id_empresa"]
                or doc.get("tipo_documento") != "merma"):
            return {"error": "No encontrado"}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.exists(ruta):
            return {"error": "No encontrado"}, 404
        return send_file(ruta)
