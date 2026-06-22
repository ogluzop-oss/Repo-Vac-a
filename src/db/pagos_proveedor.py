"""
Pagos a proveedores (rama Tesorería, FASE 4).

Réplica del patrón `ventas_cobros` (db/cobros.py) para el lado AP: pagos parciales,
completos y múltiples contra una factura de compra. Si se indica una cuenta bancaria,
registra además el movimiento de tesorería (PAGO) y abona el vencimiento PAGO asociado
(best-effort, idempotente). No modifica las tablas de compras.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("pagos_proveedor_db")

METODOS = ("transferencia", "efectivo", "tarjeta", "domiciliacion", "confirming", "otros")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _filas(cur):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def registrar_pago(id_factura_compra, metodo, importe, *, id_proveedor=None, referencia=None,
                   estado="pagado", id_cuenta=None, fecha=None, usuario=None,
                   id_empresa=None) -> int | None:
    """Registra un pago a proveedor. Si `id_cuenta`, genera el movimiento de tesorería
    (PAGO, salida) y abona el vencimiento PAGO del documento. Devuelve el id del pago."""
    id_empresa = _emp(id_empresa)
    if metodo not in METODOS:
        metodo = "otros"
    importe = round(float(importe or 0), 2)
    import datetime as _dt
    f = fecha or _dt.date.today().strftime("%Y-%m-%d")
    if hasattr(f, "strftime"):
        f = f.strftime("%Y-%m-%d")
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pagos_proveedor (id_empresa, id_factura_compra, id_proveedor, metodo, "
                "importe, referencia, estado, id_cuenta, fecha, usuario) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_factura_compra, id_proveedor, metodo, importe, referencia,
                 estado, id_cuenta, f, usuario))
            pid = cur.lastrowid
            conn.commit()
    except Exception as e:
        logger.error("registrar_pago: %s", e)
        return None
    # Integraciones best-effort (no rompen el registro del pago).
    if estado == "pagado":
        if id_cuenta is not None:
            try:
                from src.db import tesoreria as TES
                TES.registrar_movimiento("PAGO", -abs(importe), id_cuenta=id_cuenta, fecha=f,
                                         concepto=f"Pago proveedor (factura {id_factura_compra})",
                                         referencia=referencia, origen="pago_proveedor",
                                         id_documento=f"PP:{pid}", idempotente=True,
                                         usuario=usuario, id_empresa=id_empresa)
            except Exception as e:
                logger.debug("mov tesorería pago: %s", e)
        _abonar_vencimiento(id_factura_compra, importe, usuario, id_empresa)
    _audit(usuario, "pago_proveedor", f"id={pid} factura={id_factura_compra} {importe}")
    return pid


def _abonar_vencimiento(id_factura_compra, importe, usuario, id_empresa):
    """Abona el vencimiento PAGO asociado a la factura de compra (si existe)."""
    try:
        from src.db import vencimientos as V
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT numero_factura FROM compras_facturas WHERE id_factura=%s AND id_empresa=%s",
                        (id_factura_compra, id_empresa))
            r = cur.fetchone()
        numero = (r[0] if r and not isinstance(r, dict) else (r.get("numero_factura") if r else None))
        doc = f"FCMP:{numero or id_factura_compra}"
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM vencimientos WHERE id_empresa=%s AND origen='compra_factura' "
                        "AND tipo='PAGO' AND id_documento=%s LIMIT 1", (id_empresa, doc))
            rv = cur.fetchone()
        if rv:
            vid = rv[0] if not isinstance(rv, dict) else list(rv.values())[0]
            V.abonar(vid, importe, usuario=usuario, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("_abonar_vencimiento: %s", e)


def pagos_de_factura(id_factura_compra, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM pagos_proveedor WHERE id_factura_compra=%s AND id_empresa=%s "
                        "ORDER BY id", (id_factura_compra, id_empresa))
            return _filas(cur)
    except Exception as e:
        logger.error("pagos_de_factura: %s", e)
        return []


def total_pagado(id_factura_compra, id_empresa=None) -> float:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(importe),0) FROM pagos_proveedor WHERE "
                        "id_factura_compra=%s AND id_empresa=%s AND estado='pagado'",
                        (id_factura_compra, id_empresa))
            r = cur.fetchone()
            return round(float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0), 2)
    except Exception as e:
        logger.error("total_pagado: %s", e)
        return 0.0


def saldo_pendiente(id_factura_compra, total_factura, id_empresa=None) -> float:
    """Total de la factura menos lo ya pagado (>0 = queda por pagar)."""
    return round(float(total_factura or 0) - total_pagado(id_factura_compra, id_empresa), 2)


def desglose_por_metodo(id_empresa=None, desde=None, hasta=None) -> dict:
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "estado='pagado'"], [id_empresa]
    if desde:
        cond.append("fecha>=%s"); params.append(desde)
    if hasta:
        cond.append("fecha<=%s"); params.append(hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT metodo, COALESCE(SUM(importe),0) FROM pagos_proveedor "
                        f"WHERE {' AND '.join(cond)} GROUP BY metodo", params)
            out = {}
            for r in cur.fetchall():
                d = list((r if isinstance(r, dict) else dict(zip([c[0] for c in cur.description], r))).values())
                out[d[0]] = round(float(d[1]), 2)
            return out
    except Exception as e:
        logger.error("desglose_por_metodo: %s", e)
        return {}


def _audit(usuario, accion, detalles):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(usuario or "sistema", accion, "pagos_proveedor", detalles)
    except Exception as e:
        logger.debug("audit %s: %s", accion, e)
