"""
INV.3 · Lotes, caducidades y FEFO.

Entrada de lotes, consumo FEFO (caducidad próxima primero, sin caducidad al final),
alertas de caducidad, trazabilidad por lote, integración end-to-end con venta/merma/
inventario/recepción, multiempresa y GUI.
"""

import datetime as _dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import lotes as L
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

HOY = _dt.date.today()


def _cad(dias):
    return (HOY + _dt.timedelta(days=dias)).isoformat()


def _limpia(db, cod=None, emp=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        if cod:
            cur.execute("DELETE FROM lotes WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (cod,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
        if emp and emp != EMPRESA_DEFAULT_ID:
            cur.execute("DELETE FROM lotes WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _art(fab, db, **kw):
    cod = fab.articulo(**kw)
    fab.al_limpiar(lambda: _limpia(db, cod))
    return cod


# ── Entrada + consumo FEFO ───────────────────────────────────────────────────
def test_fefo_orden(db, fab):
    cod = _art(fab, db, stock_tienda=30)
    L.registrar_entrada(cod, "A", 10, fecha_caducidad=_cad(5), id_empresa=EMPRESA_DEFAULT_ID)
    L.registrar_entrada(cod, "B", 10, fecha_caducidad=_cad(60), id_empresa=EMPRESA_DEFAULT_ID)
    L.registrar_entrada(cod, "C", 10, id_empresa=EMPRESA_DEFAULT_ID)  # sin caducidad → al final
    r = L.consumir_fefo(cod, 15, id_empresa=EMPRESA_DEFAULT_ID, id_documento="V1")
    assert r["consumido"] == 15 and r["faltante"] == 0
    assert [(d["lote"], d["consumido"]) for d in r["detalle"]] == [("A", 10), ("B", 5)]
    restos = {l["lote"]: l["cantidad"] for l in L.stock_por_lote(cod, id_empresa=EMPRESA_DEFAULT_ID)}
    assert restos == {"B": 5, "C": 10}        # A agotado


def test_fefo_insuficiente_no_bloquea(db, fab):
    cod = _art(fab, db)
    L.registrar_entrada(cod, "U", 5, id_empresa=EMPRESA_DEFAULT_ID)
    r = L.consumir_fefo(cod, 12, id_empresa=EMPRESA_DEFAULT_ID)
    assert r["consumido"] == 5 and r["faltante"] == 7        # consume lo disponible


def test_consumo_sin_lotes_es_noop(db, fab):
    cod = _art(fab, db)
    r = L.consumir_fefo(cod, 5, id_empresa=EMPRESA_DEFAULT_ID)
    assert r["consumido"] == 0 and r["faltante"] == 5 and r["detalle"] == []


def test_entrada_acumula_lote(db, fab):
    cod = _art(fab, db)
    id1 = L.registrar_entrada(cod, "X", 5, id_empresa=EMPRESA_DEFAULT_ID)
    id2 = L.registrar_entrada(cod, "X", 7, id_empresa=EMPRESA_DEFAULT_ID)
    assert id1 == id2                                         # mismo lote acumula
    assert L.stock_total_en_lotes(cod, id_empresa=EMPRESA_DEFAULT_ID) == 12


# ── Alertas de caducidad ─────────────────────────────────────────────────────
def test_alertas(db, fab):
    cod = _art(fab, db)
    L.registrar_entrada(cod, "PROX", 4, fecha_caducidad=_cad(10), id_empresa=EMPRESA_DEFAULT_ID)
    L.registrar_entrada(cod, "LEJOS", 4, fecha_caducidad=_cad(200), id_empresa=EMPRESA_DEFAULT_ID)
    L.registrar_entrada(cod, "VENC", 4, fecha_caducidad=_cad(-3), id_empresa=EMPRESA_DEFAULT_ID)
    prox = [l["lote"] for l in L.lotes_por_caducar(30, id_empresa=EMPRESA_DEFAULT_ID)]
    cad = [l["lote"] for l in L.lotes_caducados(id_empresa=EMPRESA_DEFAULT_ID)]
    assert "PROX" in prox and "LEJOS" not in prox and "VENC" not in prox
    assert "VENC" in cad


# ── Trazabilidad ─────────────────────────────────────────────────────────────
def test_trazabilidad(db, fab):
    cod = _art(fab, db)
    idl = L.registrar_entrada(cod, "T", 10, id_empresa=EMPRESA_DEFAULT_ID)
    L.consumir_fefo(cod, 4, tipo="MERMA", id_empresa=EMPRESA_DEFAULT_ID, id_documento="M1")
    tz = L.trazabilidad_lote(idl, id_empresa=EMPRESA_DEFAULT_ID)
    tipos = [m["tipo"] for m in tz]
    assert "ENTRADA" in tipos and "MERMA" in tipos
    assert len(L.trazabilidad_articulo(cod, id_empresa=EMPRESA_DEFAULT_ID)) == 2


# ── Integración end-to-end: venta → FEFO ─────────────────────────────────────
def test_venta_consume_fefo(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = _art(fab, db, stock_tienda=20)
    L.registrar_entrada(cod, "V-A", 5, fecha_caducidad=_cad(5), id_empresa=EMPRESA_DEFAULT_ID)
    L.registrar_entrada(cod, "V-B", 10, fecha_caducidad=_cad(90), id_empresa=EMPRESA_DEFAULT_ID)
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 7, "precio_unitario": 1.0}])
    assert vid
    restos = {l["lote"]: l["cantidad"] for l in L.stock_por_lote(cod, id_empresa=EMPRESA_DEFAULT_ID)}
    assert restos == {"V-B": 8}             # V-A (5) agotado + 2 de V-B


# ── Integración: merma → FEFO ────────────────────────────────────────────────
def test_merma_consume_fefo(db, fab):
    from src.db.mermas import registrar_merma
    cod = _art(fab, db, stock_total=20)
    L.registrar_entrada(cod, "M-A", 10, fecha_caducidad=_cad(3), id_empresa=EMPRESA_DEFAULT_ID)
    fab.al_limpiar(lambda: _borra_mermas(db, cod))
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        assert registrar_merma(cod, 4, "rotura", columna_stock="Stock_total")
    assert L.stock_total_en_lotes(cod, id_empresa=EMPRESA_DEFAULT_ID) == 6


def _borra_mermas(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM mermas WHERE codigo=%s", (cod,))
        conn.commit()


# ── Integración: inventario físico → ajuste lotes ────────────────────────────
def test_inventario_ajusta_lotes(db, fab):
    from src.db import inventario_fisico as INV
    cod = _art(fab, db, stock_total=10, stock_tienda=0)
    L.registrar_entrada(cod, "INV-A", 10, fecha_caducidad=_cad(20), id_empresa=EMPRESA_DEFAULT_ID)
    iid = INV.crear_inventario("inv lotes", id_empresa=EMPRESA_DEFAULT_ID)
    fab.al_limpiar(lambda: _borra_inv(db, iid))
    INV.abrir_inventario(iid, EMPRESA_DEFAULT_ID)
    INV.registrar_recuento(iid, cod, 7, id_empresa=EMPRESA_DEFAULT_ID)   # -3
    INV.cerrar_inventario(iid, usuario="ana", id_empresa=EMPRESA_DEFAULT_ID)
    assert L.stock_total_en_lotes(cod, id_empresa=EMPRESA_DEFAULT_ID) == 7   # FEFO consumió 3


def _borra_inv(db, iid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM inventarios WHERE id=%s", (iid,))
        conn.commit()


# ── Integración: recepción logística → entrada de lote ───────────────────────
def test_recepcion_registra_lote(db, fab):
    cod = _art(fab, db)
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        idl = L.registrar_entrada(cod, "REC", 0 + 5, fecha_caducidad=_cad(50),
                                  id_empresa=EMPRESA_DEFAULT_ID, origen="recepcion",
                                  id_documento="DOC1")
    assert idl
    lote = L.obtener_lote(idl, id_empresa=EMPRESA_DEFAULT_ID)
    assert lote["origen"] == "recepcion" and lote["cantidad"] == 5


# ── Multiempresa ─────────────────────────────────────────────────────────────
def test_multiempresa(db, fab):
    cod = _art(fab, db)
    emp2 = fab.empresa("LOTES B")
    fab.al_limpiar(lambda: _limpia(db, emp=emp2))
    L.registrar_entrada(cod, "E1", 5, id_empresa=EMPRESA_DEFAULT_ID)
    L.registrar_entrada(cod, "E2", 9, id_empresa=emp2)
    a = L.stock_por_lote(cod, id_empresa=EMPRESA_DEFAULT_ID)
    b = L.stock_por_lote(cod, id_empresa=emp2)
    assert len(a) == 1 and a[0]["lote"] == "E1"
    assert len(b) == 1 and b[0]["lote"] == "E2"
    # consumo en una empresa no afecta a la otra
    L.consumir_fefo(cod, 5, id_empresa=EMPRESA_DEFAULT_ID)
    assert L.stock_total_en_lotes(cod, id_empresa=emp2) == 9


# ── GUI ──────────────────────────────────────────────────────────────────────
def test_gui(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    cod = _art(fab, db)
    L.registrar_entrada(cod, "G", 6, fecha_caducidad=_cad(10), id_empresa=EMPRESA_DEFAULT_ID)
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        from src.gui.lotes_caducidades import LotesWindow
        w = LotesWindow()
        w.in_cod.setText(cod); w._buscar()
        assert w.tabla.rowCount() == 1
        w._alertas()
        assert w.tabla_al.rowCount() >= 1
        w.close()
