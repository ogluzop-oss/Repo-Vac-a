"""
Tesorería · FASE 3 — Vencimientos unificados (AR/AP, estados, integración facturas).
"""

import datetime as dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import vencimientos as V
from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


def _limpia(db, vid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM vencimientos WHERE id=%s", (vid,))
        conn.commit()


def test_ciclo_estados(db):
    vid = V.crear_vencimiento("COBRO", 100, "2026-12-31", origen="manual",
                              id_documento="M" + uuid.uuid4().hex[:6], id_empresa=E)
    try:
        assert vid
        r = V.abonar(vid, 40, id_empresa=E)
        assert r["estado"] == "PARCIAL" and r["pendiente"] == 60.0
        r = V.abonar(vid, 60, id_empresa=E)
        assert r["estado"] == "PAGADO" and r["pendiente"] == 0.0
    finally:
        _limpia(db, vid)


def test_idempotencia(db):
    doc = "DUP" + uuid.uuid4().hex[:6]
    a = V.crear_vencimiento("PAGO", 50, "2026-10-01", origen="manual", id_documento=doc, id_empresa=E)
    b = V.crear_vencimiento("PAGO", 50, "2026-10-01", origen="manual", id_documento=doc, id_empresa=E)
    try:
        assert a == b
    finally:
        _limpia(db, a)


def test_marcar_vencidos(db):
    ayer = (dt.date.today() - dt.timedelta(days=2)).strftime("%Y-%m-%d")
    vid = V.crear_vencimiento("COBRO", 10, ayer, origen="manual",
                              id_documento="V" + uuid.uuid4().hex[:6], id_empresa=E)
    try:
        assert V.marcar_vencidos(E) >= 1
        v = [x for x in V.listar_vencimientos(id_empresa=E) if x["id"] == vid][0]
        assert v["estado"] == "VENCIDO"
    finally:
        _limpia(db, vid)


def test_resumen_cobrar_pagar(db):
    c = V.crear_vencimiento("COBRO", 200, "2026-12-31", origen="manual", id_documento="RC" + uuid.uuid4().hex[:6], id_empresa=E)
    p = V.crear_vencimiento("PAGO", 80, "2026-12-31", origen="manual", id_documento="RP" + uuid.uuid4().hex[:6], id_empresa=E)
    try:
        r = V.resumen(E)
        assert r["cobrar"] >= 200 and r["pagar"] >= 80
    finally:
        _limpia(db, c); _limpia(db, p)


def test_integracion_factura_cliente(db):
    # Inserta una factura de cliente mínima y genera su vencimiento COBRO.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO facturas_cliente (id_empresa, estado, base, iva, total, cobrado, "
                    "fecha_emision, fecha_vencimiento, numero, serie) "
                    "VALUES (%s,'emitida',100,21,121,21,%s,%s,%s,'A')",
                    (E, "2026-06-01", "2026-07-01", 9001))
        fid = cur.lastrowid
        conn.commit()
    try:
        vid = V.generar_desde_factura_cliente(fid, E)
        assert vid
        v = [x for x in V.listar_vencimientos(tipo="COBRO", id_empresa=E) if x["id"] == vid][0]
        assert float(v["pendiente"]) == 100.0 and v["origen"] == "factura_cliente"   # 121-21
        # idempotente
        assert V.generar_desde_factura_cliente(fid, E) == vid
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM vencimientos WHERE id_documento LIKE %s AND id_empresa=%s", ("FC:%", E))
            cur.execute("DELETE FROM facturas_cliente WHERE id_factura=%s", (fid,))
            conn.commit()
