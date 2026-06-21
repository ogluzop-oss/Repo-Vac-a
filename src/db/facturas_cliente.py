"""
Facturación comercial de cliente (VTA.8) — capa COMERCIAL, no fiscal.

`facturas_cliente(+lineas)` con estados (borrador/emitida/cobrada/parcial/vencida/anulada),
conciliación factura↔cobro↔venta↔cliente e informes de ventas/márgenes. NO sustituye
Verifactu/Facturae (la factura fiscal se sigue emitiendo por el núcleo fiscal); esta capa
da trazabilidad comercial y rentabilidad. Multiempresa. Sin Qt.
"""

import datetime as _dt
import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion, transaccion

logger = logging.getLogger("ventas.facturas_cliente")

ESTADOS = ("borrador", "emitida", "cobrada", "parcial", "vencida", "anulada")


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def crear_factura(id_cliente=None, id_venta=None, lineas=None, base=None, iva=None,
                  serie=None, fecha_emision=None, fecha_vencimiento=None, id_empresa=None) -> int | None:
    """Crea una factura comercial. Captura coste_unitario por línea para márgenes."""
    id_empresa = _emp(id_empresa)
    lineas = lineas or []
    base_calc = round(sum(int(l.get("cantidad") or 0) * round(float(l.get("precio_unitario") or 0), 2)
                          for l in lineas), 2)
    base_f = round(float(base), 2) if base is not None else base_calc
    iva_f = round(float(iva or 0), 2)
    total_f = round(base_f + iva_f, 2)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO facturas_cliente (id_empresa, id_cliente, id_venta, serie, "
                        "estado, base, iva, total, fecha_emision, fecha_vencimiento) "
                        "VALUES (%s,%s,%s,%s,'borrador',%s,%s,%s,%s,%s)",
                        (id_empresa, id_cliente, id_venta, serie, base_f, iva_f, total_f,
                         fecha_emision, fecha_vencimiento))
            fid = cur.lastrowid
            cur.execute("UPDATE facturas_cliente SET numero=%s WHERE id_factura=%s",
                        (f"FC{fid:06d}", fid))
            for l in lineas:
                cant = int(l.get("cantidad") or 0)
                precio = round(float(l.get("precio_unitario") or 0), 2)
                coste = l.get("coste_unitario")
                if coste is None:   # toma coste medio del artículo si no se indica
                    try:
                        from src.db import compras
                        coste = float((compras.obtener_costes(l.get("codigo") or
                                       l.get("codigo_articulo")) or {}).get("coste_medio") or 0)
                    except Exception:
                        coste = 0
                cur.execute("INSERT INTO facturas_cliente_lineas (id_factura, id_empresa, "
                            "codigo_articulo, descripcion, cantidad, precio_unitario, coste_unitario, "
                            "subtotal) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (fid, id_empresa, l.get("codigo") or l.get("codigo_articulo"),
                             l.get("descripcion"), cant, precio, round(float(coste or 0), 2),
                             round(cant * precio, 2)))
            return fid
    except Exception as e:
        logger.error("crear_factura: %s", e); return None


def obtener_factura(fid, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturas_cliente WHERE id_factura=%s AND id_empresa=%s",
                        (fid, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM facturas_cliente_lineas WHERE id_factura=%s ORDER BY id", (fid,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_factura: %s", e); return None


def emitir(fid, id_empresa=None) -> bool:
    return _set_estado(fid, "emitida", id_empresa)


def anular(fid, id_empresa=None) -> bool:
    return _set_estado(fid, "anulada", id_empresa)


def _set_estado(fid, estado, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    if estado not in ESTADOS:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET estado=%s WHERE id_factura=%s AND id_empresa=%s",
                        (estado, fid, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("_set_estado: %s", e); return False


def registrar_cobro_factura(fid, importe, id_empresa=None) -> dict:
    """Suma un cobro a la factura y actualiza el estado (parcial/cobrada)."""
    id_empresa = _emp(id_empresa)
    f = obtener_factura(fid, id_empresa)
    if not f:
        return {"ok": False}
    nuevo_cobrado = round(float(f["cobrado"] or 0) + float(importe or 0), 2)
    estado = "cobrada" if nuevo_cobrado >= float(f["total"]) else "parcial"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET cobrado=%s, estado=%s WHERE id_factura=%s "
                        "AND id_empresa=%s", (nuevo_cobrado, estado, fid, id_empresa))
            conn.commit()
        return {"ok": True, "cobrado": nuevo_cobrado, "estado": estado,
                "pendiente": round(float(f["total"]) - nuevo_cobrado, 2)}
    except Exception as e:
        logger.error("registrar_cobro_factura: %s", e); return {"ok": False}


def marcar_vencidas(id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    hoy = _dt.date.today().isoformat()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET estado='vencida' WHERE id_empresa=%s "
                        "AND estado IN ('emitida','parcial') AND fecha_vencimiento IS NOT NULL "
                        "AND fecha_vencimiento < %s", (id_empresa, hoy))
            return cur.rowcount
    except Exception as e:
        logger.error("marcar_vencidas: %s", e); return 0


def listar_facturas(id_empresa=None, id_cliente=None, estado=None, limite=500) -> list:
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [id_empresa]
    if id_cliente:
        cond.append("id_cliente=%s"); params.append(id_cliente)
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM facturas_cliente WHERE {' AND '.join(cond)} "
                        f"ORDER BY id_factura DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_facturas: %s", e); return []


# ── Informes de ventas / márgenes / rentabilidad ─────────────────────────────
def informe_margenes(desde=None, hasta=None, id_empresa=None) -> dict:
    """Margen = Σ(precio - coste)·cantidad sobre las líneas de venta del período."""
    id_empresa = _emp(id_empresa)
    cond, params = ["v.id_empresa=%s"], [id_empresa]
    if desde:
        cond.append("v.fecha>=%s"); params.append(desde)
    if hasta:
        cond.append("v.fecha<=%s"); params.append(str(hasta) + " 23:59:59" if len(str(hasta)) == 10 else hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"""
                SELECT COALESCE(SUM(vi.subtotal),0) AS ventas,
                       COALESCE(SUM(vi.cantidad * COALESCE(a.coste_medio,0)),0) AS coste
                FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id
                LEFT JOIN articulos a ON a.codigo=vi.codigo_articulo
                WHERE {' AND '.join(cond)}
            """, params)
            r = cur.fetchone()
            ventas = float((r[0] if not isinstance(r, dict) else r["ventas"]) or 0)
            coste = float((r[1] if not isinstance(r, dict) else r["coste"]) or 0)
        margen = round(ventas - coste, 2)
        pct = round(margen / ventas * 100, 2) if ventas else 0.0
        return {"ventas": round(ventas, 2), "coste": round(coste, 2), "margen": margen,
                "margen_pct": pct}
    except Exception as e:
        logger.error("informe_margenes: %s", e); return {"ventas": 0, "coste": 0, "margen": 0}


def ventas_por_cliente(desde=None, hasta=None, id_empresa=None, limite=50) -> list:
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "cliente_id IS NOT NULL"], [id_empresa]
    if desde:
        cond.append("fecha>=%s"); params.append(desde)
    if hasta:
        cond.append("fecha<=%s"); params.append(str(hasta) + " 23:59:59" if len(str(hasta)) == 10 else hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT cliente_id, COALESCE(cliente_nombre,'') nombre, COUNT(*) n, "
                        f"COALESCE(SUM(total),0) total FROM ventas WHERE {' AND '.join(cond)} "
                        f"GROUP BY cliente_id, cliente_nombre ORDER BY total DESC LIMIT %s",
                        (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("ventas_por_cliente: %s", e); return []
