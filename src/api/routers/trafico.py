"""
Router /traffic — ingesta en segundo plano de sensores de conteo de personas (tráfico exterior/
passerby + entradas efectivas), para alimentar el Capture Rate en "Resumen de Ventas" (petición
explícita). Sin vista propia: es un endpoint de ingesta puro, pensado para que el sensor/pasarela
(webhook HTTP POST) empuje sus lecturas agregadas.

Autenticación: REUTILIZA tal cual el mecanismo M2M ya existente (`api.security.requiere_auth`,
`X-API-Key` + `X-Empresa-Id`) — no se crea ningún catálogo de claves por sensor/dispositivo nuevo
(auditoría previa: no existía ninguno). El `store_id` del payload (INT `tiendas.id` o el
`codigo_tienda` legible, p. ej. "TND-001") ata la lectura a la tienda DENTRO de la empresa ya
autenticada por la cabecera — aislamiento de tenant real, sin inventar infraestructura nueva.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.post("/traffic/readings")
    @requiere_auth()
    def trafico_ingesta():
        from flask import g, jsonify, request
        from src.db import trafico_sensores as T
        from src.db.tiendas import tienda_de_codigo

        d = request.get_json(silent=True) or {}
        store_id = d.get("store_id")
        timestamp = d.get("timestamp")
        passerby_count = d.get("passerby_count")
        entry_count = d.get("entry_count")
        if store_id is None or timestamp is None or passerby_count is None or entry_count is None:
            return jsonify({"ok": False, "error": "faltan_campos",
                           "detalle": "store_id, timestamp, passerby_count y entry_count son obligatorios."}), 400

        id_empresa = g.ctx["id_empresa"]
        # `store_id` puede llegar como el id INT interno o como el código legible de tienda
        # (p. ej. "TND-001") — mismo criterio de resolución que ya usa el resto de la API móvil/
        # portal (`db.tiendas.tienda_de_codigo`), sin inventar una segunda convención.
        id_tienda = None
        try:
            id_tienda = int(store_id)
        except (TypeError, ValueError):
            id_tienda = tienda_de_codigo(str(store_id), id_empresa=id_empresa)
        if id_tienda is None:
            return jsonify({"ok": False, "error": "store_id_no_reconocido"}), 404

        try:
            passerby_count = int(passerby_count)
            entry_count = int(entry_count)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "passerby_count/entry_count deben ser enteros."}), 400

        r = T.registrar_lectura(
            id_empresa, id_tienda, timestamp, passerby_count, entry_count,
            bucket_minutos=int(d.get("bucket_minutos") or T.BUCKET_MINUTOS_POR_DEFECTO),
            fuente=d.get("source") or d.get("fuente"))
        return jsonify(r), (201 if r.get("ok") else 400)

    @bp.get("/traffic/summary")
    @requiere_auth()
    def trafico_resumen():
        """Resumen agregado (passerby/entries/capture_rate) por rango de fechas — espejo REST del
        mismo cálculo que alimenta la franja de KPIs de "Resumen de Ventas" en escritorio, para
        consumidores externos (móvil/portal) que quieran el mismo dato."""
        from flask import g, jsonify, request
        from src.db import trafico_sensores as T

        desde = request.args.get("desde")
        hasta = request.args.get("hasta") or desde
        if not desde:
            return jsonify({"ok": False, "error": "faltan_fechas"}), 400
        id_tienda = request.args.get("id_tienda")
        resumen = T.resumen_periodo(
            desde, hasta, id_empresa=g.ctx["id_empresa"],
            id_tienda=int(id_tienda) if id_tienda else None)
        return jsonify(resumen)
