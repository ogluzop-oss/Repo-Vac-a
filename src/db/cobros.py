"""
Cobros avanzados (VTA.4) — pago mixto / parcial / diferido.

`ventas_cobros` permite varias líneas de cobro por venta (efectivo, tarjeta, transferencia,
paypal, stripe, redsys, monedero, cupón). Aditivo: NO sustituye `ventas.forma_pago` (que se
conserva para compatibilidad con TPV/cierre Z). Multiempresa. Sin Qt.
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ventas.cobros")

METODOS = ("efectivo", "tarjeta", "transferencia", "paypal", "stripe", "redsys",
           "monedero", "cupon", "otros")


def _emp(id_empresa=None):
    # IOC v3 (Bloque V): seam de identidad delegado en la fachada de datos (db -> db).
    try:
        from src.db.identidad_contexto import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        try:
            from src.db.empresa import empresa_actual_id
            return id_empresa or empresa_actual_id()
        except Exception:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return id_empresa or EMPRESA_DEFAULT_ID


def registrar_cobro(id_venta, metodo, importe, referencia=None, estado="cobrado",
                    id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    if metodo not in METODOS:
        metodo = "otros"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ventas_cobros (id_empresa, id_venta, metodo, importe, "
                        "referencia, estado) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_venta, metodo, round(float(importe or 0), 2),
                         referencia, estado))
            conn.commit()
            _cobro_id = cur.lastrowid
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("COBRO_REGISTRADO", id_empresa=id_empresa, origen="tesoreria",
                         ref_entidad="cobro", ref_id=_cobro_id,
                         payload={"id_venta": id_venta, "metodo": metodo,
                                  "importe": round(float(importe or 0), 2)})
        except Exception:
            pass
        return _cobro_id
    except Exception as e:
        logger.error("registrar_cobro: %s", e); return None


def cobros_de_venta(id_venta, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ventas_cobros WHERE id_venta=%s AND id_empresa=%s ORDER BY id",
                        (id_venta, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("cobros_de_venta: %s", e); return []


def total_cobrado(id_venta, id_empresa=None) -> float:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(importe),0) FROM ventas_cobros WHERE id_venta=%s "
                        "AND id_empresa=%s AND estado='cobrado'", (id_venta, id_empresa))
            r = cur.fetchone()
            return round(float((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0), 2)
    except Exception as e:
        logger.error("total_cobrado: %s", e); return 0.0


def saldo_pendiente(id_venta, total_venta, id_empresa=None) -> float:
    """Total de la venta menos lo cobrado (>0 = pago diferido/parcial pendiente)."""
    return round(float(total_venta or 0) - total_cobrado(id_venta, id_empresa), 2)


def cobrar_pendiente(id_venta, total_venta, metodo="efectivo", referencia=None, id_empresa=None) -> dict:
    """'Cobro express' de FACTURACIÓN (ledger, NO pasarela): registra en 1 paso el SALDO PENDIENTE de la
    venta/factura como cobrado, reutilizando `registrar_cobro`. Idempotente: si ya está saldada (saldo<=0)
    no registra nada. Devuelve {ok, importe, idempotente|error}. Distinto de `pagos.cobrar_express`
    (que cobra un pedido online por pasarela): aquí solo se asienta el cobro en el ledger."""
    emp = _emp(id_empresa)
    saldo = saldo_pendiente(id_venta, total_venta, emp)
    if saldo <= 0.005:
        return {"ok": True, "importe": 0.0, "idempotente": True}     # ya cobrada por completo
    cid = registrar_cobro(id_venta, metodo, saldo, referencia=referencia, id_empresa=emp)
    if not cid:
        return {"ok": False, "error": "no se pudo registrar el cobro"}
    return {"ok": True, "importe": saldo, "id_cobro": cid, "metodo": metodo}


def desglose_por_metodo(id_empresa=None, desde=None, hasta=None) -> dict:
    """Suma de cobros por método (para arqueo/cierre Z y conciliación)."""
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "estado='cobrado'"], [id_empresa]
    if desde:
        cond.append("fecha>=%s"); params.append(desde)
    if hasta:
        cond.append("fecha<=%s"); params.append(str(hasta) + " 23:59:59" if len(str(hasta)) == 10 else hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT metodo, COALESCE(SUM(importe),0) FROM ventas_cobros "
                        f"WHERE {' AND '.join(cond)} GROUP BY metodo", params)
            return {(r[0] if not isinstance(r, dict) else list(r.values())[0]):
                    float((r[1] if not isinstance(r, dict) else list(r.values())[1]) or 0)
                    for r in cur.fetchall()}
    except Exception as e:
        logger.error("desglose_por_metodo: %s", e); return {}
