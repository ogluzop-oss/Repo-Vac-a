"""
Router /sat — mis tickets asignados, iniciar, registrar una intervención CON foto obligatoria y
resolver — Rediseño móvil · Grupo B, módulo 4. `intervenciones.registrar_intervencion` es una inserción
independiente del estado del ticket (un ticket puede llevar varias visitas antes de resolverse), por eso
la foto se enlaza POR INTERVENCIÓN (`referencia=f"INTERVENCION:{id}"`), no por ticket — cada visita
tiene su propia evidencia. Mismo patrón de dos pasos que `losses.py`/`gmao.py`/`calidad.py`.

Investigado y descartado un pad de firma: `partes_tecnicos.firmado`/`ruta_pdf` (`intervenciones.
crear_parte`) no los llama nadie ni los lee nadie hoy — es el stub muerto de una futura función de PDF
firmado digitalmente, no una foto de evidencia. No se tocan.

Igual que Calidad, se aplican los permisos RBAC ya existentes en el catálogo (`tickets.gestionar`,
`intervenciones.gestionar`) vía `requiere_auth(permiso)`.
"""

from src.api.security import requiere_auth

_ESTADOS_ABIERTOS_EXCLUIDOS = ("resuelto", "cerrado")


def _guardar_foto_intervencion(iid, id_empresa, id_usuario, file_storage):
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("sat")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"INTERVENCION_{iid}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="intervencion", referencia=f"INTERVENCION:{iid}",
        hash_documental=h, id_empresa=id_empresa, id_tienda=None, id_usuario=id_usuario)


def registrar(bp):
    @bp.get("/sat/tickets")
    @requiere_auth()
    def sat_mis_tickets():
        from flask import g, jsonify
        from src.services.sat import tickets
        eid = g.ctx["id_empresa"]
        todos = tickets.listar(tecnico=g.ctx["usuario"].get("id"), id_empresa=eid)
        abiertos = [t for t in todos if t.get("estado") not in _ESTADOS_ABIERTOS_EXCLUIDOS]
        return jsonify(abiertos)

    @bp.post("/sat/tickets/<int:id_ticket>/start")
    @requiere_auth("tickets.gestionar")
    def sat_iniciar_ticket(id_ticket):
        from flask import g, jsonify
        from src.services.sat import tickets
        try:
            r = tickets.cambiar_estado(id_ticket, "en_proceso", id_empresa=g.ctx["id_empresa"])
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/sat/tickets/<int:id_ticket>/interventions")
    @requiere_auth()
    def sat_listar_intervenciones(id_ticket):
        from flask import g, jsonify
        from src.db.documentos import obtener_por_referencia
        from src.services.sat import intervenciones
        eid = g.ctx["id_empresa"]
        filas = intervenciones.listar(id_ticket=id_ticket, id_empresa=eid)
        for f in filas:
            doc = obtener_por_referencia(f"INTERVENCION:{f['id']}", id_empresa=eid)
            f["id_documento_foto"] = doc["id_documento"] if doc else None
        return jsonify(filas)

    @bp.post("/sat/tickets/<int:id_ticket>/interventions")
    @requiere_auth("intervenciones.gestionar")
    def sat_registrar_intervencion(id_ticket):
        from flask import g, jsonify, request
        from src.services.sat import intervenciones
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Foto de la intervención obligatoria"}), 400
        d = request.form
        try:
            horas = float(d.get("horas") or 0)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Horas inválidas"}), 400
        eid = g.ctx["id_empresa"]
        iid = intervenciones.registrar_intervencion(
            id_ticket=id_ticket, tecnico=g.ctx["usuario"].get("id"), tipo=d.get("tipo") or "visita",
            descripcion=d.get("descripcion"), horas=horas, id_empresa=eid)
        if not iid:
            return jsonify({"ok": False, "error": "No se pudo registrar la intervención"}), 400
        id_doc = _guardar_foto_intervencion(iid, eid, g.ctx["usuario"].get("id"), foto)
        if not id_doc:
            return jsonify({"ok": False, "error": "No se pudo guardar la foto"}), 400
        return jsonify({"ok": True, "intervencion": iid, "id_documento": id_doc}), 201

    @bp.post("/sat/tickets/<int:id_ticket>/resolve")
    @requiere_auth("tickets.gestionar")
    def sat_resolver_ticket(id_ticket):
        from flask import g, jsonify
        from src.services.sat import tickets
        try:
            r = tickets.cambiar_estado(id_ticket, "resuelto", id_empresa=g.ctx["id_empresa"])
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/sat/tickets/photo/<id_documento>")
    @requiere_auth()
    def sat_foto_intervencion(id_documento):
        import os

        from flask import g, send_file
        from src.db.documentos import obtener_documento
        doc = obtener_documento(id_documento)
        if (not doc or doc.get("id_empresa") != g.ctx["id_empresa"]
                or doc.get("tipo_documento") != "intervencion"):
            return {"error": "No encontrado"}, 404
        ruta = doc.get("ruta")
        if not ruta or not os.path.exists(ruta):
            return {"error": "No encontrado"}, 404
        return send_file(ruta)
