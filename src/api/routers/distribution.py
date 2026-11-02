"""
Router /distribution — dos dominios DISTINTOS, fusionados en la misma pantalla móvil "Pedidos" a
petición del usuario (antes "Picking pedidos"), pero con motores de backend separados, sin mezclar
lógica de negocio:

  · Pedidos B2B mayoristas (`/distribution/orders`, `/distribution/picking/...`, `/distribution/
    carriers`): pedido de cliente → picking → ruta → expedición. Esto es lo que el escritorio llama
    "Distribución" (`gui/distribucion_gui.py`), NO la tabla plana `pedidos` (recepción de palet, sin
    ningún escritor en escritorio). Expone `services.expediciones` + `db.clientes` tal cual.

  · Pedidos ONLINE de la tienda web/Click&Collect (`/distribution/online-orders/...`): ciclo
    PAGADO→PREPARANDO→ENVIADO→ENTREGADO de `services.tpv.online_orders_service` (el mismo motor que ya
    usa el Portal Web de escritorio tras "Venta almacén") — NO tiene relación con el motor B2B de
    arriba, son dos sistemas de pedidos completamente distintos que solo comparten pantalla en móvil.

Todo tenant-scoped desde `g.ctx["id_empresa"]`. Alcance móvil deliberadamente recortado en "Nuevo
pedido" (B2B): el cliente se BUSCA entre los ya existentes (`buscar_clientes`) — el alta de cliente
nuevo se queda en escritorio.

Sin permiso RBAC dedicado todavía: exige solo autenticación, igual que el resto de endpoints móviles.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/distribution/orders")
    @requiere_auth()
    def distribution_listar():
        from flask import g, jsonify, request
        from src.services import expediciones as _E
        estado = request.args.get("estado") or None
        return jsonify(_E.listar_pedidos(g.ctx["id_empresa"], estado=estado))

    @bp.get("/distribution/orders/<int:id_pedido>")
    @requiere_auth()
    def distribution_detalle(id_pedido):
        from flask import g, jsonify
        from src.db import ventas_comercial as VC
        ped = VC.obtener_pedido_cliente(id_pedido, id_empresa=g.ctx["id_empresa"])
        if not ped:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify(ped)

    @bp.post("/distribution/orders")
    @requiere_auth()
    def distribution_crear():
        from flask import g, jsonify, request
        from src.services import expediciones as _E
        d = request.get_json(silent=True) or {}
        id_cliente = d.get("id_cliente")
        if not id_cliente:
            return jsonify({"ok": False, "error": "Indica el cliente."}), 400
        pid = _E.crear_pedido(id_cliente, d.get("lineas") or [], observaciones=d.get("observaciones"),
                              id_empresa=g.ctx["id_empresa"], usuario=g.ctx["usuario"].get("nombre"))
        if not pid:
            return jsonify({"ok": False, "error": "No se pudo crear el pedido."}), 400
        return jsonify({"ok": True, "id": pid}), 201

    @bp.get("/distribution/customers")
    @requiere_auth()
    def distribution_clientes():
        from flask import g, jsonify, request
        from src.db import clientes as _C
        texto = request.args.get("q", "")
        return jsonify(_C.buscar_clientes(texto, id_empresa=g.ctx["id_empresa"]))

    @bp.post("/distribution/orders/<int:id_pedido>/picking")
    @requiere_auth()
    def distribution_preparar(id_pedido):
        from flask import g, jsonify
        from src.services import expediciones as _E
        pick_id = _E.preparar(id_pedido, responsable=g.ctx["usuario"].get("nombre"),
                              id_empresa=g.ctx["id_empresa"])
        if not pick_id:
            return jsonify({"ok": False, "error": "No se pudo preparar el picking."}), 400
        return jsonify({"ok": True, "id_picking": pick_id}), 201

    @bp.get("/distribution/picking/<int:id_picking>/route")
    @requiere_auth()
    def distribution_ruta(id_picking):
        from flask import g, jsonify
        from src.services import expediciones as _E
        lineas, resumen = _E.ruta_optima(id_picking, id_empresa=g.ctx["id_empresa"])
        return jsonify({"lineas": lineas, "resumen": resumen})

    @bp.get("/distribution/carriers")
    @requiere_auth()
    def distribution_transportistas():
        from flask import g, jsonify
        from src.services import expediciones as _E
        return jsonify(_E.listar_transportistas(g.ctx["id_empresa"]))

    @bp.post("/distribution/orders/<int:id_pedido>/dispatch")
    @requiere_auth()
    def distribution_expedir(id_pedido):
        from flask import g, jsonify, request
        from src.services import expediciones as _E
        d = request.get_json(silent=True) or {}
        r = _E.expedir(id_pedido, id_transportista=d.get("id_transportista"),
                       direccion=d.get("direccion"), id_empresa=g.ctx["id_empresa"],
                       usuario=g.ctx["usuario"].get("nombre"))
        return (jsonify(r), 200) if r.get("ok") else (jsonify(r), 400)

    # ── Pedidos ONLINE (tienda web/Click&Collect) — motor `online_orders_service`, sin relación con
    #    el B2B de arriba (ver docstring del módulo). ──
    def _pedido_online_de_la_empresa(id_pedido, id_empresa):
        from src.services.tpv import online_orders_service as _OS
        ped = _OS.obtener_pedido(id_pedido)
        if not ped or ped.get("id_empresa") != id_empresa:
            return None
        return ped

    @bp.get("/distribution/online-orders")
    @requiere_auth()
    def distribution_online_listar():
        from flask import g, jsonify, request
        from src.db import stock_almacen as _SA
        from src.db import tiendas as _T
        from src.services.tpv import online_orders_service as _OS
        estado = request.args.get("estado") or None
        # Contexto del empleado autenticado: su tienda (destino habitual) y su almacén (origen de
        # encargos que sirve, aunque el destino sea otra tienda) — mismo mecanismo de resolución
        # que el Portal Web de escritorio (`backend/portal_empleado_web.py`), a partir del mismo
        # `centro_codigo` que ya expone `g.ctx["usuario"]` (ver `api/security.py`/`logistics.py`).
        centro_codigo = g.ctx["usuario"].get("centro_codigo")
        id_tienda = _T.tienda_de_codigo(centro_codigo, g.ctx["id_empresa"]) if centro_codigo else None
        id_almacen_origen = (_SA.almacen_de_codigo_centro(centro_codigo, g.ctx["id_empresa"])
                             if centro_codigo else None)
        pedidos = _OS.listar_pedidos_online(id_empresa=g.ctx["id_empresa"], id_tienda=id_tienda,
                                            estado=estado, id_almacen_origen=id_almacen_origen)
        # Etiqueta barata (sin tocar online_orders_service): marca los pedidos que se ven por ser
        # ORIGEN del encargo (destino = otra tienda), para que el móvil pueda distinguirlos de un
        # pedido local normal sin necesitar un campo nuevo en el motor.
        if id_tienda is not None:
            cache_nombres = {}
            for p in pedidos:
                destino = p.get("id_tienda")
                es_origen = destino is not None and destino != id_tienda
                p["es_encargo_origen"] = es_origen
                if es_origen:
                    if destino not in cache_nombres:
                        try:
                            from src.db.tiendas import obtener_tienda
                            t = obtener_tienda(destino) or {}
                            cache_nombres[destino] = t.get("nombre") or t.get("codigo_tienda")
                        except Exception:
                            cache_nombres[destino] = None
                    p["tienda_destino_nombre"] = cache_nombres[destino]
        return jsonify(pedidos)

    @bp.get("/distribution/online-orders/<id_pedido>")
    @requiere_auth()
    def distribution_online_detalle(id_pedido):
        from flask import g, jsonify
        ped = _pedido_online_de_la_empresa(id_pedido, g.ctx["id_empresa"])
        if not ped:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify(ped)

    @bp.post("/distribution/online-orders/<id_pedido>/prepare")
    @requiere_auth()
    def distribution_online_preparar(id_pedido):
        from flask import g, jsonify
        from src.services.tpv import online_orders_service as _OS
        if not _pedido_online_de_la_empresa(id_pedido, g.ctx["id_empresa"]):
            return jsonify({"ok": False, "error": "No encontrado"}), 404
        ok = _OS.cambiar_estado(id_pedido, "PREPARANDO")
        return jsonify({"ok": ok}), (200 if ok else 400)

    @bp.post("/distribution/online-orders/<id_pedido>/ship")
    @requiere_auth()
    def distribution_online_enviar(id_pedido):
        from flask import g, jsonify, request
        from src.services.tpv import online_orders_service as _OS
        if not _pedido_online_de_la_empresa(id_pedido, g.ctx["id_empresa"]):
            return jsonify({"ok": False, "error": "No encontrado"}), 404
        d = request.get_json(silent=True) or {}
        # Mismo orden de llamadas que el Portal Web de escritorio (`gui/portal_web_home.py`).
        ok = _OS.cambiar_estado(id_pedido, "ENVIADO")
        if ok:
            _OS.registrar_envio(id_pedido, d.get("transportista", ""), d.get("seguimiento", ""))
        return jsonify({"ok": ok}), (200 if ok else 400)

    @bp.post("/distribution/online-orders/<id_pedido>/deliver")
    @requiere_auth()
    def distribution_online_entregar(id_pedido):
        from flask import g, jsonify
        from src.services.tpv import online_orders_service as _OS
        if not _pedido_online_de_la_empresa(id_pedido, g.ctx["id_empresa"]):
            return jsonify({"ok": False, "error": "No encontrado"}), 404
        ok = _OS.cambiar_estado(id_pedido, "ENTREGADO")
        return jsonify({"ok": ok}), (200 if ok else 400)
