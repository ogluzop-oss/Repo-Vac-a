"""Router /portal-proveedor — API del PORTAL DE PROVEEDOR (lado proveedor, enlace bidireccional).

PREPARADO Y DEGRADABLE: se cablea siempre (para poder probarse y quedar listo), pero el enlace remoto en
vivo no se despliega hasta producción (`portal.portal_activo()` es informativo). La autenticación es por
TOKEN de portal (cabecera `X-Portal-Token`), que resuelve al tenant + proveedor vía
`portal.resolver_token` — cada proveedor solo ve y toca SUS datos (aislamiento). No contiene lógica: delega
en `services.compras.portal`.
"""

import functools


def _proveedor_ctx():
    """Resuelve el token de portal a {id_empresa, id_proveedor, estado} o None."""
    from flask import request
    from src.services.compras import portal
    tok = request.headers.get("X-Portal-Token")
    return portal.resolver_token(tok) if tok else None


def requiere_proveedor(fn):
    """Exige un token de portal válido (no revocado). Fija g.portal = {id_empresa, id_proveedor}."""
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
        ctx = _proveedor_ctx()
        if not ctx:
            return jsonify({"error": "unauthorized"}), 401
        from src.services.compras import portal
        portal.marcar_conexion(request.headers.get("X-Portal-Token"))
        g.portal = ctx
        return fn(*a, **k)
    return wrapper


def registrar(bp):
    from flask import g, jsonify, request
    from src.services.compras import portal

    def _emp():
        return g.portal["id_empresa"]

    def _prov():
        return g.portal["id_proveedor"]

    @bp.get("/portal-proveedor/me")
    @requiere_proveedor
    def me():
        return jsonify({"id_proveedor": _prov(), "estado": g.portal.get("estado"),
                        "modo": portal.modo()})

    # ── Tarifas (el proveedor sube su lista de precios) ──
    @bp.get("/portal-proveedor/tarifas")
    @requiere_proveedor
    def tarifas():
        return jsonify({"data": portal.listar_tarifas(_prov(), id_empresa=_emp())})

    @bp.put("/portal-proveedor/tarifas")
    @requiere_proveedor
    def subir_tarifa():
        b = request.get_json(silent=True) or {}
        if not b.get("codigo") or b.get("precio") is None:
            return jsonify({"error": "codigo y precio requeridos"}), 400
        tid = portal.subir_tarifa(_prov(), b["codigo"], b["precio"],
                                  unidad_medida=b.get("unidad_medida", "unidad"),
                                  descuento=b.get("descuento", 0),
                                  cantidad_minima=b.get("cantidad_minima", 1), id_empresa=_emp())
        return (jsonify({"ok": bool(tid), "id": tid}), 200 if tid else 500)

    # ── Stock declarado ──
    @bp.put("/portal-proveedor/stock")
    @requiere_proveedor
    def stock():
        b = request.get_json(silent=True) or {}
        if not b.get("codigo") or b.get("stock") is None:
            return jsonify({"error": "codigo y stock requeridos"}), 400
        ok = portal.set_stock(_prov(), b["codigo"], b["stock"],
                              unidad_medida=b.get("unidad_medida", "unidad"), id_empresa=_emp())
        return (jsonify({"ok": ok}), 200 if ok else 500)

    # ── Pedidos del proveedor + estado ──
    @bp.get("/portal-proveedor/pedidos")
    @requiere_proveedor
    def pedidos():
        return jsonify({"data": portal.pedidos_de_proveedor(_prov(), id_empresa=_emp())})

    @bp.put("/portal-proveedor/pedidos/<int:id_pedido>/estado")
    @requiere_proveedor
    def estado_pedido(id_pedido):
        b = request.get_json(silent=True) or {}
        ok = portal.actualizar_estado_pedido(id_pedido, b.get("estado", "pendiente"),
                                             nota=b.get("nota"), id_proveedor=_prov(), id_empresa=_emp())
        return (jsonify({"ok": ok}), 200 if ok else 400)

    # ── RFQ (el proveedor ve las abiertas y oferta) ──
    @bp.get("/portal-proveedor/rfq")
    @requiere_proveedor
    def rfq_abiertas():
        return jsonify({"data": portal.rfq_abiertas(id_empresa=_emp())})

    @bp.post("/portal-proveedor/rfq/<int:id_rfq>/oferta")
    @requiere_proveedor
    def ofertar(id_rfq):
        b = request.get_json(silent=True) or {}
        if b.get("precio") is None:
            return jsonify({"error": "precio requerido"}), 400
        oid = portal.responder_rfq(id_rfq, _prov(), b["precio"],
                                   unidad_medida=b.get("unidad_medida", "unidad"),
                                   plazo_dias=b.get("plazo_dias"),
                                   observaciones=b.get("observaciones"), id_empresa=_emp())
        return (jsonify({"ok": bool(oid), "id": oid}), 200 if oid else 400)

    # ── Mensajería (el proveedor lee su hilo y escribe) ──
    @bp.get("/portal-proveedor/mensajes")
    @requiere_proveedor
    def mensajes():
        id_pedido = request.args.get("id_pedido", type=int)
        return jsonify({"data": portal.hilo(_prov(), id_pedido=id_pedido, id_empresa=_emp())})

    @bp.post("/portal-proveedor/mensajes")
    @requiere_proveedor
    def enviar_mensaje():
        b = request.get_json(silent=True) or {}
        if not (b.get("cuerpo") or "").strip():
            return jsonify({"error": "cuerpo requerido"}), 400
        mid = portal.enviar_mensaje(_prov(), b["cuerpo"], id_pedido=b.get("id_pedido"),
                                    autor="proveedor", id_empresa=_emp())
        return (jsonify({"ok": bool(mid), "id": mid}), 200 if mid else 500)
