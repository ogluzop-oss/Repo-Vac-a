"""
Presupuestos y pedidos de cliente (VTA.6) — flujo comercial previo a la venta.

Presupuesto → (aprobar) → pedido de cliente → (convertir) → venta. Reserva de stock
best-effort (marca de línea). Reutiliza `conexion.registrar_venta_con_items` para la venta
final. Multiempresa/multitienda. Sin Qt.
"""

import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion, transaccion

logger = logging.getLogger("ventas.comercial")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def _tienda():
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


def _crear_doc(doc, id_cliente, lineas, observaciones, usuario, id_empresa, id_origen=None):
    id_empresa = _emp(id_empresa)
    lineas = lineas or []
    tabla = f"ventas_{doc}"
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO {tabla} (id_empresa, id_cliente, id_tienda, estado, "
                        f"observaciones, usuario, id_origen) VALUES (%s,%s,%s,'borrador',%s,%s,%s)",
                        (id_empresa, id_cliente, _tienda(), observaciones, usuario, id_origen))
            did = cur.lastrowid
            cur.execute(f"UPDATE {tabla} SET numero=%s WHERE id=%s",
                        (f"{'PRE' if doc == 'presupuestos' else 'PED'}{did:06d}", did))
            total = 0.0
            for ln in lineas:
                cant = int(ln.get("cantidad") or 0)
                precio = round(float(ln.get("precio_unitario") or 0), 2)
                sub = round(cant * precio, 2); total += sub
                cur.execute(f"INSERT INTO {tabla}_lineas (id_doc, id_empresa, codigo_articulo, "
                            f"descripcion, cantidad, precio_unitario, subtotal) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (did, id_empresa, ln.get("codigo") or ln.get("codigo_articulo"),
                             ln.get("descripcion"), cant, precio, sub))
            cur.execute(f"UPDATE {tabla} SET total=%s WHERE id=%s", (round(total, 2), did))
            return did
    except Exception as e:
        logger.error("_crear_doc(%s): %s", doc, e); return None


def _obtener(doc, did, id_empresa=None):
    id_empresa = _emp(id_empresa)
    tabla = f"ventas_{doc}"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {tabla} WHERE id=%s AND id_empresa=%s", (did, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute(f"SELECT * FROM {tabla}_lineas WHERE id_doc=%s ORDER BY id", (did,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("_obtener(%s,%s): %s", doc, did, e); return None


def _set_estado(doc, did, estado, id_empresa=None, **extra):
    id_empresa = _emp(id_empresa)
    sets = ["estado=%s"]; params = [estado]
    for k, v in extra.items():
        sets.append(f"{k}=%s"); params.append(v)
    params += [did, id_empresa]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE ventas_{doc} SET {', '.join(sets)} WHERE id=%s AND id_empresa=%s", params)
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("_set_estado(%s): %s", doc, e); return False


# ── Presupuestos ──────────────────────────────────────────────────────────────
def crear_presupuesto(id_cliente=None, lineas=None, observaciones=None, usuario=None, id_empresa=None):
    return _crear_doc("presupuestos", id_cliente, lineas, observaciones, usuario, id_empresa)


def obtener_presupuesto(did, id_empresa=None):
    return _obtener("presupuestos", did, id_empresa)


def aprobar_presupuesto(did, id_empresa=None) -> bool:
    return _set_estado("presupuestos", did, "aprobado", id_empresa)


def rechazar_presupuesto(did, id_empresa=None) -> bool:
    return _set_estado("presupuestos", did, "rechazado", id_empresa)


def convertir_a_pedido(did_presupuesto, usuario=None, id_empresa=None) -> int | None:
    """Convierte un presupuesto aprobado en pedido de cliente (reserva de stock best-effort)."""
    id_empresa = _emp(id_empresa)
    pre = _obtener("presupuestos", did_presupuesto, id_empresa)
    if not pre or pre["estado"] not in ("aprobado", "borrador"):
        return None
    lineas = [{"codigo": l["codigo_articulo"], "descripcion": l.get("descripcion"),
               "cantidad": l["cantidad"], "precio_unitario": l["precio_unitario"]} for l in pre["lineas"]]
    ped = _crear_doc("pedidos_cliente", pre.get("id_cliente"), lineas, pre.get("observaciones"),
                     usuario, id_empresa, id_origen=did_presupuesto)
    if ped:
        _set_estado("presupuestos", did_presupuesto, "convertido", id_empresa, id_venta=None)
        _reservar_stock("pedidos_cliente", ped, id_empresa)
    return ped


# ── Pedidos de cliente ────────────────────────────────────────────────────────
def crear_pedido_cliente(id_cliente=None, lineas=None, observaciones=None, usuario=None, id_empresa=None):
    pid = _crear_doc("pedidos_cliente", id_cliente, lineas, observaciones, usuario, id_empresa)
    if pid:
        _reservar_stock("pedidos_cliente", pid, id_empresa)
    return pid


def obtener_pedido_cliente(did, id_empresa=None):
    return _obtener("pedidos_cliente", did, id_empresa)


def _reservar_stock(doc, did, id_empresa):
    """Reserva best-effort: marca las líneas como reservadas (no descuenta stock real)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE ventas_{doc}_lineas SET reservado=1 WHERE id_doc=%s", (did,))
            conn.commit()
    except Exception as e:
        logger.warning("_reservar_stock(%s,%s): %s", doc, did, e)


def convertir_a_venta(did_pedido, usuario=None, id_empresa=None) -> int | None:
    """Convierte un pedido de cliente en venta real (consume stock/lotes vía el flujo TPV)."""
    id_empresa = _emp(id_empresa)
    ped = _obtener("pedidos_cliente", did_pedido, id_empresa)
    if not ped or ped["estado"] in ("convertido", "cancelado"):
        return None
    items = [{"codigo_articulo": l["codigo_articulo"], "cantidad": l["cantidad"],
              "precio_unitario": l["precio_unitario"]} for l in ped["lineas"]]
    try:
        from src.db.conexion import registrar_venta_con_items
        vid = registrar_venta_con_items(items, empleado_id=None)
        if vid:
            _set_estado("pedidos_cliente", did_pedido, "convertido", id_empresa, id_venta=vid)
        return vid
    except Exception as e:
        logger.error("convertir_a_venta(%s): %s", did_pedido, e); return None


def cancelar(doc, did, id_empresa=None) -> bool:
    return _set_estado(doc, did, "cancelado", id_empresa)


def listar(doc, id_empresa=None, estado=None, limite=500) -> list:
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM ventas_{doc} WHERE {' AND '.join(cond)} "
                        f"ORDER BY id DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar(%s): %s", doc, e); return []
