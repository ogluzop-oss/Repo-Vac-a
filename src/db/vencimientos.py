"""
Vencimientos unificados (rama Tesorería, FASE 3).

Motor único de cuentas a cobrar (tipo COBRO) y a pagar (tipo PAGO) procedente de cualquier
origen: facturas de cliente (AR), facturas de compra (AP), nóminas e impuestos. Cada cobro/
pago reduce `pendiente` y avanza el estado PENDIENTE→PARCIAL→PAGADO. Idempotente por
(id_empresa, origen, tipo, id_documento). No modifica las tablas de origen.
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("vencimientos_db")

ESTADOS = ("PENDIENTE", "PARCIAL", "PAGADO", "VENCIDO", "ANULADO")
TIPOS = ("COBRO", "PAGO")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, row):
    return row if isinstance(row, dict) else dict(zip([d[0] for d in cur.description], row))


def _fecha(f):
    if f is None:
        return _dt.date.today().strftime("%Y-%m-%d")
    return f.strftime("%Y-%m-%d") if hasattr(f, "strftime") else str(f)


def crear_vencimiento(tipo, importe, fecha_vencimiento, *, origen="manual", id_documento=None,
                      tercero=None, concepto=None, idempotente=True, id_empresa=None) -> int | None:
    """Crea un vencimiento (pendiente=importe, estado PENDIENTE). Idempotente por documento."""
    id_empresa = _emp(id_empresa)
    tipo = (tipo or "").upper()
    if tipo not in TIPOS:
        logger.warning("crear_vencimiento: tipo inválido %s", tipo)
        return None
    importe = round(float(importe or 0), 2)
    fv = _fecha(fecha_vencimiento)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if idempotente and id_documento is not None:
                cur.execute("SELECT id FROM vencimientos WHERE id_empresa=%s AND origen=%s "
                            "AND tipo=%s AND id_documento=%s LIMIT 1",
                            (id_empresa, origen, tipo, str(id_documento)))
                ya = cur.fetchone()
                if ya:
                    return ya[0] if not isinstance(ya, dict) else list(ya.values())[0]
            cur.execute(
                "INSERT INTO vencimientos (id_empresa, tipo, fecha_vencimiento, importe, pendiente, "
                "estado, origen, id_documento, tercero, concepto) "
                "VALUES (%s,%s,%s,%s,%s,'PENDIENTE',%s,%s,%s,%s)",
                (id_empresa, tipo, fv, importe, importe, origen,
                 (str(id_documento) if id_documento is not None else None), tercero, concepto))
            vid = cur.lastrowid
            conn.commit()
        _audit(None, "alta_vencimiento", f"id={vid} {tipo} {importe}")
        return vid
    except Exception as e:
        if idempotente and id_documento is not None:
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("SELECT id FROM vencimientos WHERE id_empresa=%s AND origen=%s "
                                "AND tipo=%s AND id_documento=%s LIMIT 1",
                                (id_empresa, origen, tipo, str(id_documento)))
                    ya = cur.fetchone()
                    if ya:
                        return ya[0] if not isinstance(ya, dict) else list(ya.values())[0]
            except Exception:
                pass
        logger.error("crear_vencimiento: %s", e)
        return None


def abonar(id_venc, importe, *, usuario=None, id_empresa=None) -> dict | None:
    """Aplica un cobro/pago al vencimiento: reduce `pendiente` y recalcula estado
    (PARCIAL si queda saldo, PAGADO si llega a 0). Devuelve {pendiente, estado} o None."""
    id_empresa = _emp(id_empresa)
    importe = round(float(importe or 0), 2)
    if importe <= 0:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT pendiente, estado FROM vencimientos WHERE id=%s AND id_empresa=%s "
                        "FOR UPDATE", (id_venc, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            d = _fila(cur, r)
            if d["estado"] == "ANULADO":
                return None
            nuevo = round(float(d["pendiente"]) - importe, 2)
            if nuevo < 0:
                nuevo = 0.0
            estado = "PAGADO" if nuevo <= 0 else "PARCIAL"
            cur.execute("UPDATE vencimientos SET pendiente=%s, estado=%s WHERE id=%s AND id_empresa=%s",
                        (nuevo, estado, id_venc, id_empresa))
            conn.commit()
        _audit(usuario, "abono_vencimiento", f"id={id_venc} -{importe} → {estado}")
        return {"pendiente": nuevo, "estado": estado}
    except Exception as e:
        logger.error("abonar: %s", e)
        return None


def anular_vencimiento(id_venc, *, usuario=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE vencimientos SET estado='ANULADO' WHERE id=%s AND id_empresa=%s",
                        (id_venc, id_empresa))
            conn.commit()
        _audit(usuario, "anula_vencimiento", f"id={id_venc}")
        return True
    except Exception as e:
        logger.error("anular_vencimiento: %s", e)
        return False


def marcar_vencidos(id_empresa=None, hoy=None) -> int:
    """Marca como VENCIDO los pendientes/parciales cuya fecha ya pasó. Idempotente.
    Devuelve el nº de filas afectadas."""
    id_empresa = _emp(id_empresa)
    hoy = _fecha(hoy)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE vencimientos SET estado='VENCIDO' WHERE id_empresa=%s "
                        "AND estado IN ('PENDIENTE','PARCIAL') AND fecha_vencimiento < %s",
                        (id_empresa, hoy))
            n = cur.rowcount
            conn.commit()
        return n
    except Exception as e:
        logger.error("marcar_vencidos: %s", e)
        return 0


def listar_vencimientos(*, tipo=None, estado=None, desde=None, hasta=None,
                        id_empresa=None, limite=2000) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM vencimientos WHERE id_empresa=%s"
    p = [id_empresa]
    if tipo:
        q += " AND tipo=%s"; p.append(tipo.upper())
    if estado:
        q += " AND estado=%s"; p.append(estado.upper())
    if desde:
        q += " AND fecha_vencimiento>=%s"; p.append(desde)
    if hasta:
        q += " AND fecha_vencimiento<=%s"; p.append(hasta)
    q += " ORDER BY fecha_vencimiento ASC, id ASC LIMIT %s"; p.append(int(limite))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_vencimientos: %s", e)
        return []


def resumen(id_empresa=None) -> dict:
    """Totales pendientes a cobrar y a pagar (excluye PAGADO/ANULADO)."""
    id_empresa = _emp(id_empresa)
    out = {"cobrar": 0.0, "pagar": 0.0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT tipo, COALESCE(SUM(pendiente),0) FROM vencimientos "
                        "WHERE id_empresa=%s AND estado IN ('PENDIENTE','PARCIAL','VENCIDO') "
                        "GROUP BY tipo", (id_empresa,))
            for r in cur.fetchall():
                d = _fila(cur, r)
                vals = list(d.values())
                tipo, suma = vals[0], float(vals[1])
                out["cobrar" if tipo == "COBRO" else "pagar"] = round(suma, 2)
        return out
    except Exception as e:
        logger.error("resumen: %s", e)
        return out


# ─────────────────────────── Integraciones (lectura, sin modificar el origen) ───────────────────────────
def generar_desde_factura_cliente(id_factura, id_empresa=None) -> int | None:
    """Crea (idempotente) un vencimiento COBRO desde una factura de cliente.
    pendiente = total − cobrado; usa fecha_vencimiento (o emisión)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT total, cobrado, fecha_vencimiento, fecha_emision, id_cliente, "
                        "numero, serie FROM facturas_cliente WHERE id_factura=%s AND id_empresa=%s",
                        (id_factura, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            d = _fila(cur, r)
        pend = round(float(d["total"] or 0) - float(d["cobrado"] or 0), 2)
        if pend <= 0:
            return None
        fv = d["fecha_vencimiento"] or d["fecha_emision"]
        doc = f"FC:{d.get('serie') or ''}{d.get('numero') or id_factura}"
        return crear_vencimiento("COBRO", pend, fv, origen="factura_cliente", id_documento=doc,
                                 tercero=(f"cliente:{d['id_cliente']}" if d.get("id_cliente") else None),
                                 concepto="Factura de cliente", id_empresa=id_empresa)
    except Exception as e:
        logger.error("generar_desde_factura_cliente: %s", e)
        return None


def generar_desde_compra(id_factura_compra, id_empresa=None, dias_pago=0) -> int | None:
    """Crea (idempotente) un vencimiento PAGO desde una factura de compra.
    Vencimiento = fecha_factura + dias_pago."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT total, fecha_factura, id_proveedor, numero_factura "
                        "FROM compras_facturas WHERE id_factura=%s AND id_empresa=%s",
                        (id_factura_compra, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            d = _fila(cur, r)
        total = round(float(d["total"] or 0), 2)
        if total <= 0:
            return None
        base = d["fecha_factura"]
        if base and dias_pago:
            base_d = base if hasattr(base, "strftime") else _dt.datetime.strptime(str(base)[:10], "%Y-%m-%d").date()
            base = base_d + _dt.timedelta(days=int(dias_pago))
        doc = f"FCMP:{d.get('numero_factura') or id_factura_compra}"
        return crear_vencimiento("PAGO", total, base, origen="compra_factura", id_documento=doc,
                                 tercero=(f"proveedor:{d['id_proveedor']}" if d.get("id_proveedor") else None),
                                 concepto="Factura de compra", id_empresa=id_empresa)
    except Exception as e:
        logger.error("generar_desde_compra: %s", e)
        return None


def _audit(usuario, accion, detalles):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria(usuario or "sistema", accion, "vencimientos", detalles)
    except Exception as e:
        logger.debug("audit %s: %s", accion, e)
