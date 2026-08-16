"""Router /lonja-vendedor — API del PORTAL DEL VENDEDOR de la Lonja (mercado B2B).

PREPARADO Y DEGRADABLE. Auth por TOKEN de vendedor (cabecera `X-Lonja-Token`, vía `lonja.resolver_token`).
El vendedor define su DIVISA (referencia con la que publica) y gestiona sus LISTADOS (precio de compra
directa + puja mínima + cantidad). Cada vendedor solo ve/toca lo suyo. No contiene lógica: delega en
`services.lonja`.
"""

import functools


def requiere_vendedor(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        from flask import g, jsonify, request
        try:
            from src.seguridad import rate_limit
            clave = f"{request.remote_addr or '?'}:{request.path}"
            if not rate_limit.permitido(clave, 240, 60):
                return jsonify({"error": "rate_limited"}), 429
        except Exception:
            pass
        from src.services import lonja
        ctx = lonja.resolver_token(request.headers.get("X-Lonja-Token"))
        if not ctx:
            return jsonify({"error": "unauthorized"}), 401
        g.vendedor = ctx
        return fn(*a, **k)
    return wrapper


def registrar(bp):
    from flask import g, jsonify, request
    from src.services import lonja

    def _vid():
        return g.vendedor["id"]

    @bp.get("/lonja-vendedor/panel")
    def lv_panel():
        # Página del panel web del vendedor (SPA autocontenida). Pública: la autentican los endpoints
        # (X-Lonja-Token). Preparada para el día del despliegue; funciona en local igualmente.
        from flask import Response
        from src.services.lonja.panel_html import panel_html
        return Response(panel_html(), mimetype="text/html")

    @bp.get("/lonja-vendedor/me")
    @requiere_vendedor
    def lv_me():
        return jsonify({"id": _vid(), "nombre": g.vendedor.get("nombre"),
                        "divisa": g.vendedor.get("divisa")})

    @bp.put("/lonja-vendedor/divisa")
    @requiere_vendedor
    def lv_divisa():
        b = request.get_json(silent=True) or {}
        if not b.get("divisa"):
            return jsonify({"error": "divisa requerida"}), 400
        ok = lonja.set_divisa(_vid(), b["divisa"])
        return (jsonify({"ok": ok}), 200 if ok else 500)

    @bp.get("/lonja-vendedor/listados")
    @requiere_vendedor
    def lv_listados():
        return jsonify({"data": lonja.listar_listados(id_vendedor=_vid(), solo_activos=False)})

    @bp.post("/lonja-vendedor/listados")
    @requiere_vendedor
    def lv_publicar():
        b = request.get_json(silent=True) or {}
        if not b.get("codigo") or b.get("precio") is None:
            return jsonify({"error": "codigo y precio requeridos"}), 400
        lid = lonja.publicar(_vid(), b["codigo"], b["precio"],
                             divisa=b.get("divisa"), puja_minima=b.get("puja_minima", 0),
                             cantidad=b.get("cantidad", 1), unidad_medida=b.get("unidad_medida", "unidad"),
                             descripcion=b.get("descripcion"),
                             permite_compra_directa=b.get("permite_compra_directa", True),
                             permite_puja=b.get("permite_puja", True), fecha_limite=b.get("fecha_limite"),
                             duracion_horas=b.get("duracion_horas"), precio_reserva=b.get("precio_reserva"),
                             incremento_minimo=b.get("incremento_minimo", 0))
        return (jsonify({"ok": bool(lid), "id": lid}), 200 if lid else 500)

    @bp.delete("/lonja-vendedor/listados/<int:id_listado>")
    @requiere_vendedor
    def lv_retirar(id_listado):
        l = lonja.obtener_listado(id_listado)
        if not l or l.get("id_vendedor") != _vid():
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": lonja.retirar(id_listado)})
