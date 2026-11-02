"""
Router /logistics — Logística (Ajuste post-lanzamiento · Módulo 8): las 6 pestañas reales de escritorio
(`gui/recepcion_pale.py`) — Recepción, Traspasos (creación), Preparación (picking), Expediciones,
Incidencias e Historial — todas sobre `documentos_logisticos`/`_pales`/`_lineas`/`incidencias_logisticas`
(`src/db/logistica.py`), vía `services.logistica.traspasos`.

`GET /logistics/transfers?estado=` sirve, con distinto `estado`, tanto Traspasos-historial como
Preparación (`EN PREPARACION`) y Expediciones (`ABIERTOS`) — `db.logistica.obtener_historial_traspasos`
ya acepta cualquier estado exacto además de los sentinels `ABIERTOS`/`TODOS`, no hace falta un endpoint
por pestaña.

IMPORTANTE — dos conceptos distintos que comparten nombre parecido, no confundir:
- `g.ctx["usuario"]["centro_codigo"]` (claim JWT `tienda`, ver `api/security.py`) es
  `usuarios.tienda_id`: un CÓDIGO DE CENTRO en texto libre (p. ej. "ALMC", "TND-001") — el mismo valor
  que escritorio usa como `codigo_local`/`centro_receptor`/`origen`. Se usa AQUÍ solo para resolver
  automáticamente el `origen` de un traspaso nuevo y el `centro_receptor` al recibir un palé — nunca
  como filtro de fila.
- El parámetro `id_tienda` que aceptan `db.logistica.*` (p. ej. `obtener_historial_traspasos`) es la
  columna `documentos_logisticos.id_tienda` (INT, FK a `tiendas.id`) — un concepto DISTINTO, de
  aislamiento multi-tienda dentro de la empresa. El JWT no lleva ese id numérico (limitación conocida,
  ya señalada en fases anteriores) — se pasa `None` en todas las llamadas de solo alcance/consulta de
  este router (igual de honesto que el resto de módulos: se aísla por empresa, no por tienda concreta).

Los endpoints usados exclusivamente por la pestaña Traspaso/Preparación (listar con estado, crear,
marcar picking de línea y confirmar picking) exigen el permiso RBAC `logistica.traspasos` — mismo permiso
que ya bloquea esa función a OPERARIO en escritorio (`gui/recepcion_pale.py`) y en la app móvil
(`GET /me/modules`), reforzado aquí también en el backend (antes solo se ocultaba en la UI). Recepción
(`/logistics/pallets/<id>/expected`, `/logistics/receive`) e Incidencias siguen sin permiso dedicado
(igual que `/losses`/`/location`/`/articles`/`/labels`/`/replenishment`): exigen solo autenticación.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/logistics/transfers")
    @requiere_auth("logistica.traspasos")
    def logistics_listar():
        from flask import g, jsonify, request
        from src.services.logistica import traspasos
        estado = request.args.get("estado", "ABIERTOS")
        texto = request.args.get("q", "")
        limite = int(request.args.get("limite", 50))
        r = traspasos.listar(g.ctx["id_empresa"], None, estado=estado, texto=texto, limite=limite)
        return jsonify(r)

    @bp.get("/logistics/transfers/<id_documento>")
    @requiere_auth()
    def logistics_detalle(id_documento):
        from flask import g, jsonify
        from src.services.logistica import traspasos
        r = traspasos.detalle(id_documento, g.ctx["id_empresa"], None)
        if not r:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify(r)

    @bp.post("/logistics/transfers")
    @requiere_auth("logistica.traspasos")
    def logistics_crear():
        from flask import g, jsonify, request
        from src.services.logistica import traspasos
        body = request.get_json(silent=True) or {}
        destino = str(body.get("destino") or "").strip()
        pales = body.get("pales") or {}
        if not destino or not pales:
            return jsonify({"error": "destino y pales son obligatorios"}), 400
        origen = g.ctx["usuario"].get("centro_codigo")
        if not origen:
            return jsonify({"error": "tu perfil no tiene tienda/almacén asociado"}), 400
        r = traspasos.crear(g.ctx["id_empresa"], origen, g.ctx["usuario"].get("nombre") or "Móvil",
                            destino, body.get("agencia") or "PROPIA", body.get("observaciones") or "",
                            pales)
        if not r:
            return jsonify({"error": "No se pudo crear el traspaso"}), 400
        return jsonify(r), 201

    @bp.get("/logistics/pallets/<id_pale>/expected")
    @requiere_auth()
    def logistics_items_esperados(id_pale):
        from flask import g, jsonify
        from src.services.logistica import traspasos
        r = traspasos.items_esperados(id_pale, g.ctx["id_empresa"], None)
        return jsonify(r)

    @bp.post("/logistics/receive")
    @requiere_auth()
    def logistics_recibir():
        from flask import g, jsonify, request
        from src.services.logistica import traspasos
        body = request.get_json(silent=True) or {}
        id_pale = str(body.get("id_pale") or "").strip()
        if not id_pale:
            return jsonify({"error": "id_pale es obligatorio"}), 400
        centro_receptor = g.ctx["usuario"].get("centro_codigo")
        if not centro_receptor:
            return jsonify({"error": "tu perfil no tiene tienda/almacén asociado"}), 400
        items = body.get("items")
        if items is None:
            items = traspasos.items_esperados(id_pale, g.ctx["id_empresa"], None)
        r = traspasos.recibir(id_pale, centro_receptor, g.ctx["usuario"].get("nombre") or "Móvil",
                              items, g.ctx["id_empresa"], None)
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.post("/logistics/transfers/<id_documento>/lines/<int:id_linea>/pick")
    @requiere_auth("logistica.traspasos")
    def logistics_marcar_picking(id_documento, id_linea):
        from flask import g, jsonify, request
        from src.services.logistica import traspasos
        body = request.get_json(silent=True) or {}
        pickeado = bool(body.get("pickeado", True))
        ok = traspasos.marcar_picking(id_documento, id_linea, pickeado, g.ctx["id_empresa"], None)
        if not ok:
            return jsonify({"error": "No se pudo actualizar la línea"}), 404
        return jsonify({"ok": True})

    @bp.post("/logistics/transfers/<id_documento>/confirm-picking")
    @requiere_auth("logistica.traspasos")
    def logistics_confirmar_picking(id_documento):
        from flask import g, jsonify
        from src.services.logistica import traspasos
        r = traspasos.confirmar_picking(id_documento, g.ctx["usuario"].get("nombre") or "Móvil",
                                        g.ctx["id_empresa"], None)
        return jsonify(r), (200 if r.get("ok") else 400)

    @bp.get("/logistics/incidents")
    @requiere_auth()
    def logistics_incidencias_listar():
        from flask import g, jsonify, request
        from src.services.logistica import traspasos
        estado = request.args.get("estado")
        texto = request.args.get("q", "")
        r = traspasos.listar_incidencias(g.ctx["id_empresa"], estado, texto)
        return jsonify(r)

    @bp.post("/logistics/incidents")
    @requiere_auth()
    def logistics_incidencias_crear():
        from flask import g, jsonify, request
        from src.services.logistica import traspasos
        body = request.get_json(silent=True) or {}
        id_documento = str(body.get("id_documento") or "").strip()
        tipo = str(body.get("tipo") or "").strip()
        if not id_documento or not tipo:
            return jsonify({"error": "id_documento y tipo son obligatorios"}), 400
        iid = traspasos.crear_incidencia(
            g.ctx["id_empresa"], id_documento, tipo, body.get("descripcion") or "",
            g.ctx["usuario"].get("nombre") or "Móvil", id_pale=body.get("id_pale"),
            codigo=body.get("codigo"), cantidad=body.get("cantidad") or 0)
        if not iid:
            return jsonify({"error": "No se pudo registrar la incidencia"}), 400
        return jsonify({"ok": True, "id": iid}), 201

    @bp.post("/logistics/incidents/<int:id_incidencia>/close")
    @requiere_auth()
    def logistics_incidencias_cerrar(id_incidencia):
        from flask import g, jsonify
        from src.services.logistica import traspasos
        ok = traspasos.cerrar_incidencia(g.ctx["id_empresa"], id_incidencia)
        if not ok:
            return jsonify({"error": "No se pudo cerrar la incidencia"}), 404
        return jsonify({"ok": True})
