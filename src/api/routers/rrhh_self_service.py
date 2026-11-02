"""
Router /rrhh/me — AUTOSERVICIO móvil del empleado (petición explícita: nóminas/certificados,
vacaciones, documentos pendientes de firma, gastos de viaje con foto+OCR, "desde el móvil").
Fachada ÚNICA: `src.rrhh.portal_servicio` (la misma que ya usa el Portal del Empleado de
escritorio) — ningún motor paralelo, solo una superficie REST sobre lo ya existente. Seguridad:
todo se resuelve por el `id_usuario` del JWT → `empleados.obtener_por_usuario`; un empleado NUNCA
puede ver ni tocar el expediente de otro (no hay ningún parámetro `id_empleado` aceptado desde el
cliente en ningún endpoint)."""


def _empleado_o_403():
    """Resuelve el empleado del usuario autenticado o devuelve (None, response_error)."""
    from flask import g, jsonify
    from src.rrhh import portal_servicio
    emp = portal_servicio.resolver_empleado(g.ctx["usuario"], g.ctx["id_empresa"])
    if not emp:
        return None, (jsonify({"ok": False, "error": "sin_expediente_empleado"}), 403)
    return emp, None


def registrar(bp):
    from src.api.security import requiere_auth

    @bp.get("/rrhh/me")
    @requiere_auth()
    def rrhh_me_panel():
        from flask import g, jsonify
        from src.rrhh import portal_servicio
        emp, err = _empleado_o_403()
        if err:
            return err
        try:
            panel = portal_servicio.panel(emp["id"], g.ctx["id_empresa"])
        except portal_servicio.AccesoDenegado as e:
            return jsonify({"ok": False, "error": str(e)}), 403
        # Nóminas/documentos: solo metadatos (nunca la ruta de fichero cruda al cliente).
        nominas = [{"id": n.get("id"), "anio": n.get("anio"), "mes": n.get("mes"),
                   "bruto": n.get("bruto"), "neto": n.get("neto"), "estado": n.get("estado")}
                  for n in panel.get("nominas", [])]
        documentos = [{"id": d.get("id"), "tipo_doc": d.get("tipo_doc"), "fecha": d.get("fecha")}
                     for d in panel.get("documentos", [])]
        pendientes = [{"id": d.get("id"), "tipo_doc": d.get("tipo_doc"),
                      "fecha": d.get("fecha"), "expira": d.get("expira")}
                     for d in panel.get("documentos_pendientes", [])]
        return jsonify({
            "personal": panel.get("personal"),
            "nominas": nominas,
            "vacaciones_saldo": panel.get("vacaciones", {}).get("saldo"),
            "vacaciones": [{"id": v.get("id"), "fecha_inicio": v.get("fecha_inicio"),
                           "fecha_fin": v.get("fecha_fin"), "dias": v.get("dias"),
                           "estado": v.get("estado")}
                          for v in panel.get("vacaciones", {}).get("lista", [])],
            "documentos": documentos,
            "documentos_pendientes": pendientes,
        })

    @bp.post("/rrhh/me/vacaciones")
    @requiere_auth()
    def rrhh_me_solicitar_vacaciones():
        from flask import g, jsonify, request
        from src.rrhh import portal_servicio, vacaciones_servicio
        emp, err = _empleado_o_403()
        if err:
            return err
        d = request.get_json(silent=True) or {}
        try:
            vid = portal_servicio.solicitar_vacaciones(
                emp["id"], d.get("fecha_inicio"), d.get("fecha_fin"), id_empresa=g.ctx["id_empresa"])
        except vacaciones_servicio.GestionLaboralError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({"ok": True, "id": vid}), 201

    @bp.post("/rrhh/me/documentos/<int:id_documento>/aceptar")
    @requiere_auth()
    def rrhh_me_aceptar_documento(id_documento):
        from flask import g, jsonify, request
        from src.rrhh import firma_servicio, portal_servicio
        emp, err = _empleado_o_403()
        if err:
            return err
        try:
            ok = portal_servicio.aceptar_documento(
                emp["id"], id_documento, usuario=g.ctx["usuario"].get("nombre"),
                ip=request.remote_addr, id_empresa=g.ctx["id_empresa"])
        except firma_servicio.FirmaError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({"ok": ok})

    @bp.post("/rrhh/me/documentos/<int:id_documento>/rechazar")
    @requiere_auth()
    def rrhh_me_rechazar_documento(id_documento):
        from flask import g, jsonify, request
        from src.rrhh import firma_servicio, portal_servicio
        emp, err = _empleado_o_403()
        if err:
            return err
        d = request.get_json(silent=True) or {}
        try:
            ok = portal_servicio.rechazar_documento(
                emp["id"], id_documento, usuario=g.ctx["usuario"].get("nombre"),
                ip=request.remote_addr, motivo=d.get("motivo"), id_empresa=g.ctx["id_empresa"])
        except firma_servicio.FirmaError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify({"ok": ok})

    @bp.get("/rrhh/me/documentos/<int:id_documento>/pdf")
    @requiere_auth()
    def rrhh_me_descargar_documento(id_documento):
        """Descarga (o Nómina) de UN documento PROPIO — nunca sirve la ruta cruda: el fichero se
        descifra en memoria si está cifrado en reposo (repositorio cifrado de nóminas/
        certificados) antes de enviarlo, y nunca se expone la ruta real del servidor."""
        from flask import g, jsonify, send_file
        from src.rrhh.db import documentos as rrhh_docs
        emp, err = _empleado_o_403()
        if err:
            return err
        doc = rrhh_docs.obtener_documento(id_documento, g.ctx["id_empresa"])
        if not doc or doc.get("id_empleado") != emp["id"]:
            return jsonify({"ok": False, "error": "documento_no_encontrado"}), 404
        ruta = doc.get("ref_documento")
        import os
        if not ruta or not os.path.isfile(ruta):
            return jsonify({"ok": False, "error": "fichero_no_disponible"}), 404
        from src.utils import cripto
        ruta_legible = cripto.resolver_ruta_legible(ruta)
        return send_file(ruta_legible, mimetype="application/pdf", as_attachment=True,
                         download_name=f"{doc.get('tipo_doc') or 'documento'}_{id_documento}.pdf")

    @bp.get("/rrhh/me/gastos")
    @requiere_auth()
    def rrhh_me_listar_gastos():
        from flask import g, jsonify, request
        from src.rrhh import portal_servicio
        emp, err = _empleado_o_403()
        if err:
            return err
        estado = request.args.get("estado")
        return jsonify(portal_servicio.gastos_propios(emp["id"], g.ctx["id_empresa"], estado=estado))

    @bp.post("/rrhh/me/gastos/ocr")
    @requiere_auth()
    def rrhh_me_ocr_gasto():
        """Extrae un borrador (importe/fecha/categoría/concepto) de la foto de un ticket — "la IA
        propone, el humano confirma": NUNCA crea el gasto, solo devuelve el borrador editable."""
        import os
        import tempfile

        from flask import jsonify, request
        from src.services.gastos_viaje import ticket_ocr
        foto = request.files.get("foto") if request.files else None
        if not foto or not foto.filename:
            return jsonify({"ok": False, "error": "Foto del ticket obligatoria"}), 400
        suffix = os.path.splitext(foto.filename)[1] or ".jpg"
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(foto.read())
            r = ticket_ocr.extraer_ticket(tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return jsonify(r), (200 if r.get("ok") else 422)

    @bp.post("/rrhh/me/gastos")
    @requiere_auth()
    def rrhh_me_crear_gasto():
        from flask import g, jsonify, request
        from src.rrhh import portal_servicio
        from src.services.gastos_viaje import gastos as gastos_srv
        emp, err = _empleado_o_403()
        if err:
            return err
        d = request.form if request.files else (request.get_json(silent=True) or {})
        ruta_ticket = None
        ocr_origen = str(d.get("ocr_origen") or "").lower() in ("1", "true", "si")
        foto = request.files.get("foto") if request.files else None
        if foto and foto.filename:
            ruta_ticket = _guardar_ticket_gasto(emp["id"], g.ctx["id_empresa"], foto)
        try:
            r = portal_servicio.registrar_gasto_propio(
                emp["id"], d.get("fecha_gasto"), d.get("categoria"), d.get("importe"),
                concepto=d.get("concepto"), ruta_ticket=ruta_ticket, ocr_origen=ocr_origen,
                id_empresa=g.ctx["id_empresa"])
        except gastos_srv.GastoViajeError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        return jsonify(r), (201 if r.get("ok") else 400)


def _guardar_ticket_gasto(id_empleado, id_empresa, file_storage):
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    carpeta = ruta_datos("gastos_viaje")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    ruta = os.path.join(carpeta, f"TICKET_{id_empleado}_{ts}.jpg")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    registrar_documento(ruta=ruta, tipo="otros", referencia=f"GASTO_VIAJE:{id_empleado}:{ts}",
                        id_empresa=id_empresa)
    return ruta
