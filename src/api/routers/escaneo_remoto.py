"""
Router /remote-scan — delegación universal de escaneo QR/código de barras de escritorio a móvil.
Escritorio crea una solicitud y sondea su estado; se DIFUNDE a todos los móviles de la misma tienda/
almacén (`centro_codigo`, ver `services/escaneo_remoto.py`); el primero en reclamarla (`/claim`) es el
único que puede completarla. Sin push/SSE — sondeo REST corto.

Sin permiso RBAC dedicado (no existe `escaneo_remoto.*`/`remote_scan.*` en el catálogo) — igual que
GMAO/Transporte, exige solo autenticación. El aislamiento real es `centro_codigo` para ver la
solicitud y `reclamada_por` para completarla/cancelarla, verificado en el propio servicio.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.post("/remote-scan/requests")
    @requiere_auth()
    def remote_scan_crear():
        from flask import g, jsonify, request
        from src.services import escaneo_remoto
        d = request.get_json(silent=True) or {}
        r = escaneo_remoto.crear_solicitud(
            g.ctx["usuario"].get("id"), contexto=d.get("contexto"), id_empresa=g.ctx["id_empresa"],
            centro_codigo=g.ctx["usuario"].get("centro_codigo"), tipo=d.get("tipo", "codigo"))
        return jsonify(r), (201 if r.get("ok") else 400)

    @bp.get("/remote-scan/requests/<id_solicitud>")
    @requiere_auth()
    def remote_scan_obtener(id_solicitud):
        from flask import g, jsonify
        from src.services import escaneo_remoto
        fila = escaneo_remoto.obtener_solicitud(id_solicitud, id_empresa=g.ctx["id_empresa"])
        if not fila:
            return jsonify({"error": "No encontrada"}), 404
        return jsonify(fila)

    @bp.get("/remote-scan/pending")
    @requiere_auth()
    def remote_scan_pendientes():
        """Solicitudes vivas para DIFUNDIR en la tienda/almacén del usuario autenticado (no las suyas
        propias — las de TODA su tienda, sin reclamar todavía por nadie)."""
        from flask import g, jsonify
        from src.services import escaneo_remoto
        filas = escaneo_remoto.listar_pendientes_tienda(
            g.ctx["usuario"].get("centro_codigo"), id_empresa=g.ctx["id_empresa"])
        return jsonify(filas)

    @bp.post("/remote-scan/requests/<id_solicitud>/claim")
    @requiere_auth()
    def remote_scan_reclamar(id_solicitud):
        """El móvil reclama la solicitud al aceptar el aviso — atómico: solo uno gana la carrera."""
        from flask import g, jsonify
        from src.services import escaneo_remoto
        r = escaneo_remoto.reclamar_solicitud(
            id_solicitud, g.ctx["usuario"].get("id"), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 409)

    @bp.post("/remote-scan/requests/<id_solicitud>/complete")
    @requiere_auth()
    def remote_scan_completar(id_solicitud):
        from flask import g, jsonify, request
        from src.services import escaneo_remoto
        d = request.get_json(silent=True) or {}
        r = escaneo_remoto.completar_solicitud(
            id_solicitud, d.get("valor"), g.ctx["usuario"].get("id"), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/remote-scan/requests/<id_solicitud>/photo")
    @requiere_auth()
    def remote_scan_completar_foto(id_solicitud):
        """Cumplimiento de una solicitud `tipo='foto'`: el móvil sube la foto (multipart) en vez de un
        valor de texto. Se guarda en el registro documental (referencia temporal atada a la propia
        solicitud — el consumidor final, p. ej. Mermas en escritorio, la re-referencia a su entidad real
        una vez la conoce) y se completa la solicitud con el `id_documento` resultante como `valor`,
        reutilizando `completar_solicitud` tal cual (ya valida que quien completa es quien reclamó)."""
        import hashlib
        import os
        from datetime import datetime

        from flask import g, jsonify, request
        from src.db.documentos import registrar_documento
        from src.services import escaneo_remoto
        from src.utils.recursos import ruta_datos

        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Falta el fichero 'foto'."}), 400

        carpeta = ruta_datos("escaneo_remoto")
        os.makedirs(carpeta, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        ruta = os.path.join(carpeta, f"ESCANEO_{id_solicitud}_{ts}.jpg")
        datos = foto.read()
        if not datos:
            return jsonify({"ok": False, "error": "Foto vacía."}), 400
        with open(ruta, "wb") as f:
            f.write(datos)

        id_documento = registrar_documento(
            ruta, tipo="merma", nombre=os.path.basename(ruta), referencia=f"ESCANEO:{id_solicitud}",
            hash_documental=hashlib.sha256(datos).hexdigest(), id_empresa=g.ctx["id_empresa"],
            id_usuario=g.ctx["usuario"].get("id"))
        if not id_documento:
            return jsonify({"ok": False, "error": "No se pudo guardar la foto."}), 500

        r = escaneo_remoto.completar_solicitud(
            id_solicitud, id_documento, g.ctx["usuario"].get("id"), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/remote-scan/requests/<id_solicitud>/cancel")
    @requiere_auth()
    def remote_scan_cancelar(id_solicitud):
        from flask import g, jsonify
        from src.services import escaneo_remoto
        r = escaneo_remoto.cancelar_solicitud(
            id_solicitud, g.ctx["usuario"].get("id"), id_empresa=g.ctx["id_empresa"])
        return jsonify(r), (200 if r.get("ok") else 400)
