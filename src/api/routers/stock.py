"""
Router /stock — consulta de artículos + niveles de stock, y (Ajuste post-lanzamiento · Módulo 1) las
pestañas de escritorio que el móvil replica: Stock Almacén (desglose por almacén), Editar Stock
(admin/superadmin), Inventario (registrar recuento sobre una sesión ya abierta) y Lotes (consulta).
Todo delega en los mismos motores que usa el escritorio (`db.articulos`, `db.stock_almacen`,
`db.conexion`, `db.inventario_fisico`, `db.lotes`) — no se reimplementa ningún criterio.

Alcance deliberadamente recortado en móvil: NO se expone el ciclo de vida de inventario (crear/abrir/
cerrar/anular sesiones, decisiones de planificación) ni la entrada/consumo de lotes (acciones de
recepción más especializadas, cubiertas por Logística/Mermas) — solo consulta + el recuento diario.
"""

from src.api.paginacion import envolver, parametros
from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/stock")
    @requiere_auth("inventario.ver")
    def stock_buscar():
        from flask import g, jsonify, request
        from src.services import stock
        p = parametros()
        limite = (p["offset"] + p["limit"]) if p["activo"] else int(request.args.get("limite", 200))
        res = stock.buscar(g.ctx["id_empresa"], request.args.get("q", ""), limite=limite)
        return jsonify(envolver(res, p))

    @bp.get("/stock/warehouse")
    @requiere_auth("inventario.ver")
    def stock_almacen():
        from flask import g, jsonify, request
        from src.db import stock_almacen as SA
        codigo = (request.args.get("codigo") or "").strip()
        if not codigo:
            return jsonify({"error": "Indica el código del artículo."}), 400
        r = SA.obtener_stock_articulo(codigo, g.ctx["id_empresa"])
        return jsonify(r)

    @bp.put("/stock/edit")
    @requiere_auth("inventario.ver")
    def stock_editar():
        from flask import g, jsonify, request
        if g.ctx["usuario"].get("perfil") not in ("ADMINISTRADOR", "SUPERADMIN"):
            return jsonify({"error": "forbidden"}), 403
        from src.db.conexion import modificar_stock_completo
        d = request.get_json(silent=True) or {}
        try:
            codigo = str(d.get("codigo") or "").strip()
            central = int(d.get("stock_central") or 0)
            total = int(d.get("stock_total") or 0)
            tienda = int(d.get("stock_tienda") or 0)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Cantidades inválidas."}), 400
        if not codigo:
            return jsonify({"ok": False, "error": "Código obligatorio."}), 400
        ok = modificar_stock_completo(codigo, central, total, tienda, id_empresa=g.ctx["id_empresa"])
        return (jsonify({"ok": True}), 200) if ok else (jsonify({"ok": False}), 400)

    @bp.get("/stock/inventory/open")
    @requiere_auth("inventario.ver")
    def stock_inventarios_abiertos():
        from flask import g, jsonify
        from src.db import inventario_fisico as inv
        return jsonify(inv.inventarios_abiertos(g.ctx["id_empresa"]))

    @bp.get("/stock/inventory/<int:id_inv>/lines")
    @requiere_auth("inventario.ver")
    def stock_inventario_lineas(id_inv):
        from flask import g, jsonify
        from src.db import inventario_fisico as inv
        cab = inv.obtener_inventario(id_inv, g.ctx["id_empresa"])
        if not cab:
            return jsonify({"error": "No encontrado"}), 404
        return jsonify({"cabecera": cab, "lineas": inv.listar_lineas(id_inv, g.ctx["id_empresa"])})

    @bp.post("/stock/inventory/<int:id_inv>/count")
    @requiere_auth("inventario.ver")
    def stock_inventario_contar(id_inv):
        from flask import g, jsonify, request
        from src.db import inventario_fisico as inv
        if not inv.obtener_inventario(id_inv, g.ctx["id_empresa"]):
            return jsonify({"error": "No encontrado"}), 404
        d = request.get_json(silent=True) or {}
        codigo = str(d.get("codigo") or "").strip()
        if not codigo:
            return jsonify({"ok": False, "error": "Código obligatorio."}), 400
        try:
            contado = int(d.get("contado"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Cantidad contada inválida."}), 400
        ok = inv.registrar_recuento(id_inv, codigo, contado, d.get("observaciones"),
                                    id_empresa=g.ctx["id_empresa"])
        return (jsonify({"ok": True}), 200) if ok else (jsonify({"ok": False}), 400)

    @bp.get("/stock/lots")
    @requiere_auth("inventario.ver")
    def stock_lotes():
        from flask import g, jsonify, request
        from src.db import lotes
        codigo = request.args.get("codigo") or None
        return jsonify(lotes.listar_lotes(id_empresa=g.ctx["id_empresa"], codigo=codigo))

    @bp.get("/stock/lots/expiring")
    @requiere_auth("inventario.ver")
    def stock_lotes_caducar():
        from flask import g, jsonify, request
        from src.db import lotes
        dias = int(request.args.get("dias", 30))
        return jsonify(lotes.lotes_por_caducar(dias, id_empresa=g.ctx["id_empresa"]))
