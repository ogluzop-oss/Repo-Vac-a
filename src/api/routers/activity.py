"""
Router /activity — badges de notificación para el Dashboard móvil (+ granularidad por pestaña).

`GET /activity/badges` devuelve un contador "pendiente" para las capacidades con un concepto real
de "trabajo pendiente":

- "logistica": nº de traspasos con picking pendiente (`EN PREPARACION`) — misma fuente que alimenta
  la pestaña Traspaso (`services.logistica.traspasos.listar`).
- "pedidos": nº de pedidos B2B sin expedir (`services.expediciones.listar_pedidos`, estado
  distinto de `convertido`/`cancelado`) — mismo criterio que antes del rediseño (Módulo 4).
- "etiquetas": nº de cambios de precio recientes SIN ATENDER por el usuario
  (`services.actividad.badges.contar()`, motor general de eventos — evento `PRECIO_ACTUALIZADO`).
  ANTES contaba etiquetas ESL pendientes de sincronizar, un concepto que la pantalla móvil de
  Etiquetas (Localizar/Cambiar precio) nunca muestra — el badge no correspondía a nada visible al
  entrar (bug reportado). Ahora usa el mismo motor de eventos que ya alimenta el badge de escritorio,
  así que SIEMPRE hay algo que ver (el historial de "Cambiar precio") cuando el badge está activo.

"ubicacion" y "articulo_scan" no tienen ningún concepto real de "pendiente" a nivel de módulo (son
acciones de escaneo bajo demanda, no una bandeja) — no se les inventa un badge de módulo, pero
"ubicacion" SÍ tiene granularidad de pestaña (ver más abajo, evento `UBICACION_ASIGNADA`).

`GET /activity/subtab-badges?modulo=<v_id>` y `POST /activity/seen` dan la granularidad de PESTAÑA
dentro de un módulo (motor general de eventos, `services.actividad.badges.contar_subtabs`/
`marcar_visto`) — usados por las pantallas móviles que tienen más de una pestaña.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/activity/badges")
    @requiere_auth()
    def activity_badges():
        from flask import g, jsonify
        id_empresa = g.ctx["id_empresa"]
        usuario = g.ctx["usuario"]

        logistica_n = 0
        try:
            from src.services.logistica import traspasos as _TR
            logistica_n = len(_TR.listar(id_empresa, None, estado="EN PREPARACION", limite=200))
        except Exception:
            pass

        pedidos_n = 0
        try:
            from src.services import expediciones as _EX
            todos = _EX.listar_pedidos(id_empresa)
            pedidos_n = sum(1 for p in todos if p.get("estado") not in ("convertido", "cancelado"))
        except Exception:
            pass

        etiquetas_n = 0
        try:
            from src.services.actividad import badges as _badges
            etiquetas_n = _badges.contar(usuario=usuario, id_empresa=id_empresa).get("etiquetas", 0)
        except Exception:
            pass

        return jsonify({"logistica": logistica_n, "pedidos": pedidos_n,
                        "etiquetas": etiquetas_n})

    @bp.get("/activity/subtab-badges")
    @requiere_auth()
    def activity_subtab_badges():
        from flask import g, jsonify, request
        modulo = (request.args.get("modulo") or "").strip()
        if not modulo:
            return jsonify({"error": "modulo es obligatorio"}), 400
        try:
            from src.services.actividad import badges as _badges
            counts = _badges.contar_subtabs(modulo, usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        except Exception:
            counts = {}
        return jsonify(counts)

    @bp.post("/activity/seen")
    @requiere_auth()
    def activity_seen():
        from flask import g, jsonify, request
        body = request.get_json(silent=True) or {}
        modulo = (body.get("modulo") or "").strip()
        subtab = (body.get("subtab") or "").strip() or None
        if not modulo:
            return jsonify({"error": "modulo es obligatorio"}), 400
        clave = f"{modulo}.{subtab}" if subtab else modulo
        try:
            from src.services.actividad import badges as _badges
            ok = _badges.marcar_visto(clave, usuario=g.ctx["usuario"], id_empresa=g.ctx["id_empresa"])
        except Exception:
            ok = False
        return jsonify({"ok": bool(ok)})
