"""Operaciones críticas de la Lonja: compra directa, puja y adjudicación.

TODO va en una TRANSACCIÓN REAL con `SELECT … FOR UPDATE` sobre el listado, de modo que dos compradores
concurrentes se serialicen y NO haya doble venta. La compra directa es IDEMPOTENTE por `clave_idem`
(un reintento devuelve la misma transacción sin descontar de nuevo). Cada operación crea el pedido REAL en
el tenant comprador (reutiliza `db.compras`), así la compra fluye a Recepciones/Contabilidad como cualquier
otra. Nada de stock/pedidos paralelos.
"""

from ._common import _audit, _conn, _tx, _uno, logger


def _pedido_comprador(id_empresa, listado, cantidad, precio, usuario=None):
    """Crea (y envía) el pedido real en el tenant COMPRADOR, provisionando el proveedor si hace falta."""
    try:
        from . import vendedores as _v
        from src.db import compras as C
        from src.db import proveedores as P
        nombre = (_v.obtener(listado["id_vendedor"]) or {}).get("nombre") or f"Vendedor {listado['id_vendedor']}"
        idp = None
        for p in (P.listar_proveedores(id_empresa=id_empresa, texto=nombre) or []):
            if (p.get("razon_social") or "").strip().lower() == nombre.strip().lower():
                idp = p["id_proveedor"]; break
        if not idp:
            idp = P.crear_proveedor(nombre, id_empresa=id_empresa)
        if not idp:
            return None
        pid = C.crear_pedido(id_proveedor=idp, id_empresa=id_empresa, usuario=usuario,
                             lineas=[{"codigo": listado["codigo_articulo"], "cantidad": int(cantidad),
                                      "precio_unitario": float(precio),
                                      "descripcion": f"{listado['codigo_articulo']} · Lonja"}])
        if pid:
            C.enviar_pedido(pid, id_empresa)
        return pid
    except Exception as e:
        logger.debug("_pedido_comprador: %s", e)
        return None


def _fijar_pedido(id_transaccion, id_pedido):
    if not id_pedido:
        return
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE lonja_transacciones SET id_pedido=%s WHERE id=%s", (id_pedido, id_transaccion))
            c.commit()
    except Exception as e:
        logger.debug("_fijar_pedido: %s", e)


def comprar_directo(id_listado, id_empresa, cantidad=1, *, clave_idem=None, usuario=None) -> dict:
    """Compra directa al precio del listado. ATÓMICA (bloqueo de fila) e IDEMPOTENTE (clave_idem).
    El primero que llega se lo lleva; no hay doble venta."""
    cantidad = float(cantidad or 1)
    try:
        with _tx() as conn, conn.cursor() as cur:
            if clave_idem:
                cur.execute("SELECT id, id_pedido FROM lonja_transacciones WHERE clave_idem=%s", (clave_idem,))
                ex = _uno(cur)
                if ex:
                    return {"ok": True, "id_transaccion": ex["id"], "id_pedido": ex.get("id_pedido"),
                            "idempotente": True}
            cur.execute("SELECT * FROM lonja_listados WHERE id=%s FOR UPDATE", (id_listado,))
            l = _uno(cur)
            if not l or l["estado"] != "activo":
                return {"ok": False, "error": "listado_no_disponible"}
            if not int(l["permite_compra_directa"]):
                return {"ok": False, "error": "compra_directa_no_permitida"}
            disp = float(l["cantidad_disponible"])
            if cantidad > disp:
                return {"ok": False, "error": "cantidad_insuficiente", "disponible": disp}
            nueva = disp - cantidad
            estado = "agotado" if nueva <= 0 else "activo"
            cur.execute("UPDATE lonja_listados SET cantidad_disponible=%s, estado=%s WHERE id=%s",
                        (nueva, estado, id_listado))
            cur.execute("INSERT INTO lonja_transacciones (id_listado, id_vendedor, id_empresa, cantidad, "
                        "precio_unitario, divisa, tipo, estado, clave_idem) "
                        "VALUES (%s,%s,%s,%s,%s,%s,'compra_directa','confirmada',%s)",
                        (id_listado, l["id_vendedor"], id_empresa, cantidad, float(l["precio"]),
                         l["divisa"], clave_idem))
            tid = cur.lastrowid
        pid = _pedido_comprador(id_empresa, l, cantidad, float(l["precio"]), usuario)
        _fijar_pedido(tid, pid)
        _audit("LONJA_COMPRA", f"listado={id_listado} emp={id_empresa} tx={tid}", "lonja_transacciones")
        return {"ok": True, "id_transaccion": tid, "id_pedido": pid}
    except Exception as e:
        logger.error("comprar_directo: %s", e)
        return {"ok": False, "error": str(e)[:120]}


def mejor_puja(id_listado) -> dict | None:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_empresa, importe, divisa, estado FROM lonja_pujas "
                        "WHERE id_listado=%s AND estado IN ('pujada','ganadora') "
                        "ORDER BY importe DESC LIMIT 1", (id_listado,))
            return _uno(cur)
    except Exception as e:
        logger.error("mejor_puja: %s", e)
        return None


def pujar(id_listado, id_empresa, importe, *, divisa=None) -> dict:
    """Registra una puja de una empresa compradora. Debe ser ≥ puja mínima y mejorar la mejor puja actual
    (comparación en la divisa del listado). La puja anterior queda 'superada'."""
    importe = float(importe or 0)
    try:
        from . import divisa as _d
        with _tx() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM lonja_listados WHERE id=%s FOR UPDATE", (id_listado,))
            l = _uno(cur)
            if not l or l["estado"] != "activo":
                return {"ok": False, "error": "listado_no_disponible"}
            if not int(l["permite_puja"]):
                return {"ok": False, "error": "puja_no_permitida"}
            div = str(divisa or l["divisa"]).upper()[:8]
            importe_ref = _d.convertir(importe, div, l["divisa"])
            if importe_ref < float(l["puja_minima"]):
                return {"ok": False, "error": "por_debajo_minima", "minima": float(l["puja_minima"])}
            cur.execute("SELECT id, importe, divisa FROM lonja_pujas WHERE id_listado=%s AND estado='pujada' "
                        "ORDER BY importe DESC LIMIT 1", (id_listado,))
            mejor = _uno(cur)
            if mejor:
                mejor_ref = _d.convertir(float(mejor["importe"]), mejor["divisa"], l["divisa"])
                if importe_ref <= mejor_ref:
                    return {"ok": False, "error": "no_mejora", "mejor": mejor_ref}
                cur.execute("UPDATE lonja_pujas SET estado='superada' WHERE id_listado=%s AND estado='pujada'",
                            (id_listado,))
            cur.execute("INSERT INTO lonja_pujas (id_listado, id_empresa, importe, divisa) "
                        "VALUES (%s,%s,%s,%s)", (id_listado, id_empresa, importe, div))
            pid = cur.lastrowid
        _audit("LONJA_PUJA", f"listado={id_listado} emp={id_empresa} importe={importe}{div}", "lonja_pujas")
        return {"ok": True, "id_puja": pid}
    except Exception as e:
        logger.error("pujar: %s", e)
        return {"ok": False, "error": str(e)[:120]}


def adjudicar(id_listado, *, id_puja=None, usuario=None) -> dict:
    """Adjudica el listado a la mejor puja (o a `id_puja`): cierra la subasta, marca ganadora/rechazadas y
    crea el pedido real para la empresa ganadora."""
    try:
        with _tx() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM lonja_listados WHERE id=%s FOR UPDATE", (id_listado,))
            l = _uno(cur)
            if not l or l["estado"] not in ("activo", "agotado"):
                return {"ok": False, "error": "listado_no_adjudicable"}
            if id_puja:
                cur.execute("SELECT * FROM lonja_pujas WHERE id=%s AND id_listado=%s", (id_puja, id_listado))
            else:
                cur.execute("SELECT * FROM lonja_pujas WHERE id_listado=%s AND estado='pujada' "
                            "ORDER BY importe DESC LIMIT 1", (id_listado,))
            puja = _uno(cur)
            if not puja:
                return {"ok": False, "error": "sin_pujas"}
            cur.execute("UPDATE lonja_pujas SET estado=CASE WHEN id=%s THEN 'ganadora' ELSE 'rechazada' END "
                        "WHERE id_listado=%s AND estado IN ('pujada','superada')", (puja["id"], id_listado))
            cur.execute("UPDATE lonja_listados SET estado='adjudicado', cantidad_disponible=0 WHERE id=%s",
                        (id_listado,))
            cur.execute("INSERT INTO lonja_transacciones (id_listado, id_vendedor, id_empresa, cantidad, "
                        "precio_unitario, divisa, tipo, estado) "
                        "VALUES (%s,%s,%s,%s,%s,%s,'adjudicacion','confirmada')",
                        (id_listado, l["id_vendedor"], puja["id_empresa"], float(l["cantidad"]),
                         float(puja["importe"]), puja["divisa"]))
            tid = cur.lastrowid
            ganadora = puja["id_empresa"]
        pid = _pedido_comprador(ganadora, l, float(l["cantidad"]), float(puja["importe"]), usuario)
        _fijar_pedido(tid, pid)
        _audit("LONJA_ADJUDICA", f"listado={id_listado} ganadora={ganadora} tx={tid}", "lonja_transacciones")
        return {"ok": True, "id_transaccion": tid, "id_pedido": pid, "id_empresa_ganadora": ganadora}
    except Exception as e:
        logger.error("adjudicar: %s", e)
        return {"ok": False, "error": str(e)[:120]}


def transacciones_de(id_empresa=None, id_listado=None) -> list:
    from ._common import _filas
    cond, params = [], []
    if id_empresa:
        cond.append("id_empresa=%s"); params.append(id_empresa)
    if id_listado:
        cond.append("id_listado=%s"); params.append(id_listado)
    q = "SELECT * FROM lonja_transacciones"
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY id DESC"
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(q, tuple(params))
            return _filas(cur)
    except Exception as e:
        logger.error("transacciones_de: %s", e)
        return []
