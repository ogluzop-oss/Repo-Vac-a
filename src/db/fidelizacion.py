"""
Fidelización (VTA.3) — puntos, monedero y cupones.

Acumulación/canje de puntos y saldo de monedero del cliente, y emisión/validación/redención
de cupones con caducidad. `clientes.saldo_puntos`/`saldo_monedero` son la caché de saldo;
`fidelizacion_movimientos` el libro. Best-effort, multiempresa. Sin Qt.
"""

import datetime as _dt
import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion, transaccion

logger = logging.getLogger("ventas.fidelizacion")

PUNTOS_POR_EURO = 1   # 1 punto por € (configurable a futuro)


def _emp(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def _mov(cur, id_empresa, id_cliente, tipo, puntos=0, importe=0, id_venta=None, desc=None):
    cur.execute("INSERT INTO fidelizacion_movimientos (id_empresa, id_cliente, tipo, puntos, "
                "importe, id_venta, descripcion) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cliente, tipo, int(puntos), float(importe), id_venta, desc))


def saldo_puntos(id_cliente, id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(saldo_puntos,0) FROM clientes WHERE id=%s AND id_empresa=%s",
                        (id_cliente, id_empresa))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
    except Exception as e:
        logger.error("saldo_puntos: %s", e); return 0


def acumular_puntos(id_cliente, importe_venta, id_venta=None, id_empresa=None) -> int:
    """Acumula puntos por una venta (PUNTOS_POR_EURO). Devuelve puntos añadidos."""
    id_empresa = _emp(id_empresa)
    pts = int(float(importe_venta or 0) * PUNTOS_POR_EURO)
    if pts <= 0 or not id_cliente:
        return 0
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE clientes SET saldo_puntos=COALESCE(saldo_puntos,0)+%s "
                        "WHERE id=%s AND id_empresa=%s", (pts, id_cliente, id_empresa))
            _mov(cur, id_empresa, id_cliente, "acumular", puntos=pts, importe=importe_venta,
                 id_venta=id_venta, desc="Acumulación por venta")
        return pts
    except Exception as e:
        logger.error("acumular_puntos: %s", e); return 0


def canjear_puntos(id_cliente, puntos, id_empresa=None) -> bool:
    """Canjea puntos (resta del saldo). Falla si no hay saldo suficiente."""
    id_empresa = _emp(id_empresa)
    puntos = int(puntos)
    if puntos <= 0:
        return False
    if saldo_puntos(id_cliente, id_empresa) < puntos:
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE clientes SET saldo_puntos=saldo_puntos-%s WHERE id=%s AND id_empresa=%s",
                        (puntos, id_cliente, id_empresa))
            _mov(cur, id_empresa, id_cliente, "canjear", puntos=-puntos, desc="Canje de puntos")
        return True
    except Exception as e:
        logger.error("canjear_puntos: %s", e); return False


def revertir_puntos(id_cliente, importe_venta, id_venta=None, id_empresa=None) -> int:
    """Revierte la acumulación de una venta devuelta. Devuelve puntos retirados."""
    id_empresa = _emp(id_empresa)
    pts = int(float(importe_venta or 0) * PUNTOS_POR_EURO)
    if pts <= 0 or not id_cliente:
        return 0
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE clientes SET saldo_puntos=GREATEST(0,COALESCE(saldo_puntos,0)-%s) "
                        "WHERE id=%s AND id_empresa=%s", (pts, id_cliente, id_empresa))
            _mov(cur, id_empresa, id_cliente, "revertir", puntos=-pts, id_venta=id_venta,
                 desc="Reversión por devolución")
        return pts
    except Exception as e:
        logger.error("revertir_puntos: %s", e); return 0


def movimientos(id_cliente, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fidelizacion_movimientos WHERE id_cliente=%s AND id_empresa=%s "
                        "ORDER BY fecha DESC, id DESC", (id_cliente, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("movimientos: %s", e); return []


# ── Cupones ───────────────────────────────────────────────────────────────────
def emitir_cupon(codigo, tipo="descuento_pct", valor=0, id_cliente=None, fecha_caducidad=None,
                 id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cupones (id_empresa, codigo, id_cliente, tipo, valor, "
                        "fecha_caducidad) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, codigo, id_cliente, tipo, valor, fecha_caducidad))
            return cur.lastrowid
    except Exception as e:
        logger.error("emitir_cupon: %s", e); return None


def validar_cupon(codigo, id_empresa=None) -> dict | None:
    """Devuelve el cupón si está activo y no caducado; None en caso contrario."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cupones WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            c = _fila_a_dict(cur, cur.fetchone())
        if not c or c.get("estado") != "activo":
            return None
        cad = c.get("fecha_caducidad")
        if cad and cad < _dt.date.today():
            return None
        return c
    except Exception as e:
        logger.error("validar_cupon: %s", e); return None


def redimir_cupon(codigo, id_venta=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    c = validar_cupon(codigo, id_empresa)
    if not c:
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cupones SET estado='usado', id_venta_uso=%s WHERE id=%s AND id_empresa=%s",
                        (id_venta, c["id"], id_empresa))
        return True
    except Exception as e:
        logger.error("redimir_cupon: %s", e); return False


def expirar_cupones(id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    hoy = _dt.date.today().isoformat()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cupones SET estado='caducado' WHERE id_empresa=%s AND estado='activo' "
                        "AND fecha_caducidad IS NOT NULL AND fecha_caducidad < %s", (id_empresa, hoy))
            return cur.rowcount
    except Exception as e:
        logger.error("expirar_cupones: %s", e); return 0
