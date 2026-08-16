"""RFQ / subasta inversa: la empresa pide precio de un artículo a varios proveedores y ellos responden;
se adjudica la mejor oferta creando un pedido real.

Tablas `portal_rfq` + `portal_rfq_ofertas` (migr 0198). La ADJUDICACIÓN no crea un flujo de pedido
paralelo: reutiliza `db.compras.crear_pedido` + `enviar_pedido` (mismo motor y estados que el resto de
compras) y deja el seguimiento del proveedor en `portal_pedido_estado`.
"""

from ._common import _audit, _conn, _emp, _filas, _notificar, _uno, logger


def crear_rfq(codigo_articulo, cantidad, *, descripcion=None, unidad_medida="unidad", fecha_limite=None,
              creado_por=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO portal_rfq (id_empresa, codigo_articulo, descripcion, cantidad, "
                        "unidad_medida, fecha_limite, creado_por) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, str(codigo_articulo).strip().upper(), descripcion, float(cantidad or 1),
                         str(unidad_medida or "unidad"), fecha_limite, creado_por))
            rid = cur.lastrowid
            c.commit()
        _audit("PORTAL_RFQ_ALTA", f"{codigo_articulo}:{cantidad}", "portal_rfq")
        return rid
    except Exception as e:
        logger.error("crear_rfq: %s", e)
        return None


def listar_rfq(id_empresa=None, estado=None) -> list:
    emp = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [emp]
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, codigo_articulo, descripcion, cantidad, unidad_medida, estado, "
                        "fecha_limite, id_pedido_adjudicado, creado_en FROM portal_rfq "
                        "WHERE " + " AND ".join(cond) + " ORDER BY id DESC", tuple(params))
            return _filas(cur)
    except Exception as e:
        logger.error("listar_rfq: %s", e)
        return []


def obtener_rfq(id_rfq, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM portal_rfq WHERE id_empresa=%s AND id=%s", (emp, id_rfq))
            return _uno(cur)
    except Exception as e:
        logger.error("obtener_rfq: %s", e)
        return None


def rfq_abiertas(id_empresa=None) -> list:
    """RFQs 'abierta' visibles para los proveedores del portal (lado proveedor)."""
    return listar_rfq(id_empresa=id_empresa, estado="abierta")


def responder_rfq(id_rfq, id_proveedor, precio, *, unidad_medida="unidad", plazo_dias=None,
                  observaciones=None, id_empresa=None) -> int | None:
    """Oferta de un proveedor a una RFQ (upsert: una oferta vigente por proveedor y RFQ)."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT estado FROM portal_rfq WHERE id_empresa=%s AND id=%s", (emp, id_rfq))
            r = _uno(cur)
            if not r or r.get("estado") != "abierta":
                return None
            cur.execute("INSERT INTO portal_rfq_ofertas (id_empresa, id_rfq, id_proveedor, precio, "
                        "unidad_medida, plazo_dias, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE precio=VALUES(precio), unidad_medida=VALUES(unidad_medida), "
                        "plazo_dias=VALUES(plazo_dias), observaciones=VALUES(observaciones), "
                        "estado='ofertada', creado_en=NOW()",
                        (emp, id_rfq, id_proveedor, float(precio or 0), str(unidad_medida or "unidad"),
                         plazo_dias, observaciones))
            oid = cur.lastrowid
            c.commit()
        _notificar("rfq_oferta", "Nueva oferta en una petición de precio",
                   f"El proveedor {id_proveedor} ha ofertado en la RFQ {id_rfq}.", id_empresa=emp)
        _audit("PORTAL_RFQ_OFERTA", f"rfq={id_rfq} prov={id_proveedor} precio={precio}",
               "portal_rfq_ofertas")
        return oid
    except Exception as e:
        logger.error("responder_rfq: %s", e)
        return None


def ofertas_de_rfq(id_rfq, id_empresa=None) -> list:
    """Ofertas recibidas para una RFQ, con el nombre del proveedor, ordenadas por precio (mejor primero)."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT o.id, o.id_proveedor, "
                        "COALESCE(p.razon_social, CONCAT('Proveedor ', o.id_proveedor)) AS proveedor, "
                        "o.precio, o.unidad_medida, o.plazo_dias, o.observaciones, o.estado, o.creado_en "
                        "FROM portal_rfq_ofertas o "
                        "LEFT JOIN proveedores p ON p.id_proveedor = o.id_proveedor "
                        "WHERE o.id_empresa=%s AND o.id_rfq=%s ORDER BY o.precio ASC, proveedor ASC",
                        (emp, id_rfq))
            return _filas(cur)
    except Exception as e:
        logger.error("ofertas_de_rfq: %s", e)
        return []


def adjudicar_rfq(id_rfq, id_proveedor, *, id_empresa=None, usuario=None) -> dict:
    """Adjudica la RFQ a un proveedor: crea+envía el pedido real (motor de compras) con el precio de su
    oferta, cierra la RFQ y marca las ofertas. Devuelve {ok, id_pedido, error}."""
    from src.db import compras as C
    from .pedidos import actualizar_estado_pedido
    emp = _emp(id_empresa)
    try:
        rfq = obtener_rfq(id_rfq, emp)
        if not rfq or rfq.get("estado") != "abierta":
            return {"ok": False, "error": "rfq_no_abierta"}
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT precio, unidad_medida FROM portal_rfq_ofertas "
                        "WHERE id_empresa=%s AND id_rfq=%s AND id_proveedor=%s", (emp, id_rfq, id_proveedor))
            oferta = _uno(cur)
        if not oferta:
            return {"ok": False, "error": "sin_oferta"}
        lineas = [{"codigo": rfq["codigo_articulo"], "cantidad": int(float(rfq["cantidad"] or 1)),
                   "precio_unitario": float(oferta["precio"] or 0),
                   "descripcion": f"{rfq['codigo_articulo']} · RFQ {id_rfq}"}]
        pid = C.crear_pedido(id_proveedor=id_proveedor, lineas=lineas, id_empresa=emp, usuario=usuario)
        if not pid:
            return {"ok": False, "error": "pedido_no_creado"}
        C.enviar_pedido(pid, emp)
        actualizar_estado_pedido(pid, "pendiente", id_proveedor=id_proveedor, id_empresa=emp)
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE portal_rfq SET estado='adjudicada', id_pedido_adjudicado=%s "
                        "WHERE id_empresa=%s AND id=%s", (pid, emp, id_rfq))
            cur.execute("UPDATE portal_rfq_ofertas SET estado=CASE WHEN id_proveedor=%s THEN 'adjudicada' "
                        "ELSE 'rechazada' END WHERE id_empresa=%s AND id_rfq=%s",
                        (id_proveedor, emp, id_rfq))
            c.commit()
        _audit("PORTAL_RFQ_ADJUDICAR", f"rfq={id_rfq} prov={id_proveedor} pedido={pid}", "portal_rfq")
        return {"ok": True, "id_pedido": pid}
    except Exception as e:
        logger.error("adjudicar_rfq: %s", e)
        return {"ok": False, "error": str(e)[:120]}
