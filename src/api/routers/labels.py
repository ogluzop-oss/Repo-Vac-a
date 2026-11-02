"""
Router /labels — Etiquetas: "Localizar etiqueta ESL" (hacer parpadear una etiqueta electrónica física
para encontrarla en el lineal, sin permiso dedicado, igual que `/losses`/`/location`/`/articles`) y
"Cambiar precio + imprimir etiqueta de papel" (gateado con `etiquetas.precio.editar` — por defecto solo
ADMINISTRADOR/SUPERADMIN, ver `services/seguridad/catalogo.py`).

`GET /labels/esl/by-article` y `POST /labels/esl/locate` exponen tal cual `services.esl.registro`/
`services.esl.sync` (motor ESL ya productivo) — cero lógica nueva. `POST /labels/price` y
`GET /labels/price/<id>/pdf` exponen `services.etiquetas.pdf.cambiar_precio_y_generar` (mismo flujo que
`gui/etiquetas_precios.py`: cambia el precio Y genera el PDF con el precio nuevo).
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/labels/esl/by-article")
    @requiere_auth()
    def labels_esl_by_article():
        from flask import g, jsonify, request
        from src.services.esl import registro as _registro
        codigo = request.args.get("codigo", "")
        r = _registro.etiquetas_de_articulo(
            codigo, id_empresa=g.ctx["id_empresa"], id_tienda=g.ctx["usuario"].get("id_tienda"))
        return jsonify(r)

    @bp.post("/labels/esl/locate")
    @requiere_auth()
    def labels_esl_locate():
        from flask import g, jsonify, request
        from src.services.esl import sync as _sync
        d = request.get_json(silent=True) or {}
        label_id = d.get("label_id")
        if not label_id:
            return jsonify({"error": "label_id es obligatorio"}), 400
        r = _sync.localizar(label_id, id_empresa=g.ctx["id_empresa"],
                            id_tienda=g.ctx["usuario"].get("id_tienda"))
        return jsonify(r)

    @bp.post("/labels/price")
    @requiere_auth("etiquetas.precio.editar")
    def labels_price_cambiar():
        from flask import g, jsonify, request
        from src.services.etiquetas.pdf import cambiar_precio_y_generar
        d = request.get_json(silent=True) or {}
        r = cambiar_precio_y_generar(
            d.get("codigo"), d.get("nuevo_precio"),
            id_empresa=g.ctx["id_empresa"], id_tienda=g.ctx["usuario"].get("id_tienda"),
            id_usuario=g.ctx["usuario"].get("id"),
            formato=d.get("formato", "70x35"), tipo=d.get("tipo", "normal"))
        return (jsonify(r), 200) if r.get("ok") else (jsonify(r), 400)

    @bp.get("/labels/price/<id_documento>/pdf")
    @requiere_auth()
    def labels_price_pdf(id_documento):
        import os

        from flask import g, send_file
        from src.db.documentos import obtener_documento
        doc = obtener_documento(id_documento)
        if not doc or doc.get("id_empresa") != g.ctx["id_empresa"]:
            return {"error": "Documento no encontrado."}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.isfile(ruta):
            return {"error": "El fichero de la etiqueta ya no existe."}, 404
        return send_file(ruta, mimetype="application/pdf")
