"""
Búsqueda, localización y reimpresión de tickets de venta.

Aprovecha el identificador ampliado del ticket
(``empresa | tienda | venta | ticket | importe``) y las tablas ``ventas`` /
``venta_items`` para permitir: reimpresión, búsqueda rápida desde el TPV,
devoluciones, auditoría y recuperación de tickets antiguos. Compatible con la
arquitectura multiempresa (filtra por ``id_empresa`` cuando la columna existe).
"""

import logging
import re

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("ventas_busqueda")


def parsear_codigo_ticket(texto: str) -> dict:
    """Interpreta un texto escaneado (QR/código de barras) o tecleado y extrae
    el identificador de venta/ticket. Devuelve {venta_id, ticket_num}."""
    out = {"venta_id": None, "ticket_num": None}
    t = (texto or "").strip()
    if not t:
        return out
    # QR: SMART|TCK-...|fecha|empresa|tienda|venta|importe
    if t.upper().startswith("SMART|"):
        partes = t.split("|")
        if len(partes) >= 2 and partes[1]:
            out["ticket_num"] = partes[1]
        if len(partes) >= 6 and str(partes[5]).isdigit():
            out["venta_id"] = int(partes[5])
    if out["venta_id"] is None:
        # Código de barras / nº ticket: TCK-AAAAMMDD-#####  → venta = ##### final
        m = re.search(r"TCK-\d{8}-(\d+)", t.upper())
        if m:
            out["ticket_num"] = t if t.upper().startswith("TCK-") else out["ticket_num"]
            out["venta_id"] = int(m.group(1))
        elif t.isdigit():
            out["venta_id"] = int(t)
    return out


def _cols(cur, tabla) -> set:
    cur.execute(f"SHOW COLUMNS FROM {tabla}")
    return {r["Field"] if isinstance(r, dict) else r[0] for r in cur.fetchall()}


def buscar_ventas(texto=None, fecha_desde=None, fecha_hasta=None,
                  importe=None, id_empresa=None, limite=200) -> list[dict]:
    """Busca ventas por nº de ticket/código escaneado, rango de fechas y/o
    importe. Devuelve filas {id, fecha, total, forma_pago, empleado,
    numero_caja, n_items} ordenadas por fecha descendente."""
    filtros, params = [], []
    if texto:
        info = parsear_codigo_ticket(texto)
        if info["venta_id"] is not None:
            filtros.append("v.id = %s"); params.append(info["venta_id"])
        else:
            filtros.append("(CAST(v.id AS CHAR) LIKE %s OR v.empleado LIKE %s "
                           "OR v.cliente_nombre LIKE %s OR v.cliente_nif LIKE %s)")
            params += [f"%{texto}%"] * 4
    if fecha_desde:
        filtros.append("DATE(v.fecha) >= %s"); params.append(fecha_desde)
    if fecha_hasta:
        filtros.append("DATE(v.fecha) <= %s"); params.append(fecha_hasta)
    if importe is not None:
        filtros.append("ABS(v.total - %s) < 0.005"); params.append(float(importe))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cols = _cols(cur, "ventas")
            if "id_empresa" in cols and id_empresa:
                filtros.append("v.id_empresa = %s"); params.append(id_empresa)
            where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
            cur.execute(
                "SELECT v.id, v.fecha, v.total, v.forma_pago, v.empleado, v.numero_caja, "
                "v.cliente_nombre, "
                "(SELECT COUNT(*) FROM venta_items vi WHERE vi.venta_id = v.id) AS n_items "
                f"FROM ventas v{where} ORDER BY v.fecha DESC, v.id DESC LIMIT %s",
                (*params, int(limite)))
            filas = cur.fetchall()
            res = []
            for r in filas:
                if isinstance(r, dict):
                    res.append(r)
                else:
                    res.append({"id": r[0], "fecha": r[1], "total": r[2],
                                "forma_pago": r[3], "empleado": r[4],
                                "numero_caja": r[5], "cliente_nombre": r[6],
                                "n_items": r[7]})
            return res
    except Exception as e:
        logger.error("Error buscar_ventas: %s", e)
        return []


def obtener_venta_completa(venta_id) -> dict | None:
    """Devuelve {cabecera de venta + items} para reimpresión/devolución."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ventas WHERE id=%s", (venta_id,))
            v = cur.fetchone()
            if not v:
                return None
            if not isinstance(v, dict):
                cols = [d[0] for d in cur.description]
                v = dict(zip(cols, v))
            cur.execute(
                "SELECT codigo_articulo, nombre, seccion, cantidad, precio_unitario, subtotal "
                "FROM venta_items WHERE venta_id=%s", (venta_id,))
            items = []
            for r in cur.fetchall():
                if isinstance(r, dict):
                    items.append(r)
                else:
                    items.append({"codigo_articulo": r[0], "nombre": r[1], "seccion": r[2],
                                  "cantidad": r[3], "precio_unitario": r[4], "subtotal": r[5]})
            v["items"] = items
            return v
    except Exception as e:
        logger.error("Error obtener_venta_completa(%s): %s", venta_id, e)
        return None
