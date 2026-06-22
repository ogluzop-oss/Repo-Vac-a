"""
Tesorería · FASE 4 — Pagos a proveedores (parciales/múltiples + integración tesorería/vencimiento).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import pagos_proveedor as PP, tesoreria as T, vencimientos as V
from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"


def _factura_compra(db, total=121):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO compras_facturas (id_empresa, id_proveedor, numero_factura, "
                    "fecha_factura, base, iva, total, estado) "
                    "VALUES (%s,%s,%s,'2026-06-01',100,21,%s,'registrada')",
                    (E, 7, "FC-" + uuid.uuid4().hex[:6], total))
        fid = cur.lastrowid
        conn.commit()
    return fid


def _limpia(db, fid, cid=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM pagos_proveedor WHERE id_factura_compra=%s", (fid,))
        cur.execute("DELETE FROM vencimientos WHERE id_documento LIKE %s", (f"FCMP:%",))
        if cid:
            cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
            cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        cur.execute("DELETE FROM compras_facturas WHERE id_factura=%s", (fid,))
        conn.commit()


def test_pagos_parciales_y_saldo(db):
    fid = _factura_compra(db, total=100)
    try:
        PP.registrar_pago(fid, "transferencia", 30, id_empresa=E)
        PP.registrar_pago(fid, "transferencia", 20, id_empresa=E)
        assert PP.total_pagado(fid, E) == 50.0
        assert PP.saldo_pendiente(fid, 100, E) == 50.0
        assert len(PP.pagos_de_factura(fid, E)) == 2
    finally:
        _limpia(db, fid)


def test_pago_genera_movimiento_tesoreria(db):
    fid = _factura_compra(db, total=121)
    cid = T.crear_cuenta("Pagos", IBAN, saldo_inicial=500, id_empresa=E)
    try:
        PP.registrar_pago(fid, "transferencia", 121, id_cuenta=cid, id_empresa=E)
        # el saldo de la cuenta bajó 121
        assert T.saldo_cuenta(cid, E) == 379.0
        movs = T.listar_movimientos(id_cuenta=cid, tipo="PAGO", id_empresa=E)
        assert len(movs) == 1 and float(movs[0]["importe"]) == -121.0
    finally:
        _limpia(db, fid, cid)


def test_pago_abona_vencimiento(db):
    fid = _factura_compra(db, total=121)
    try:
        vid = V.generar_desde_compra(fid, E)        # crea vencimiento PAGO 121
        assert vid
        PP.registrar_pago(fid, "transferencia", 121, id_empresa=E)
        v = [x for x in V.listar_vencimientos(tipo="PAGO", id_empresa=E) if x["id"] == vid][0]
        assert v["estado"] == "PAGADO" and float(v["pendiente"]) == 0.0
    finally:
        _limpia(db, fid)


def test_desglose_por_metodo(db):
    fid = _factura_compra(db, total=200)
    try:
        PP.registrar_pago(fid, "transferencia", 50, fecha="2026-06-10", id_empresa=E)
        PP.registrar_pago(fid, "efectivo", 30, fecha="2026-06-10", id_empresa=E)
        d = PP.desglose_por_metodo(E, desde="2026-06-01", hasta="2026-06-30")
        assert d.get("transferencia", 0) >= 50 and d.get("efectivo", 0) >= 30
    finally:
        _limpia(db, fid)
