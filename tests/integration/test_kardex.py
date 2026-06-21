"""
INV.1 · Kárdex unificado de movimientos de stock.

Cobertura: venta→SALIDA_VENTA, devolución→DEVOLUCION, ajuste→AJUSTE (anterior/nuevo),
merma→MERMA, multiempresa, filtros del visor, historial completo, informes.
Best-effort: el registro del kárdex no rompe la operación original.
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import kardex
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant


def _limpia(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (cod,))
        conn.commit()


def _movs(db, cod, tipo=None):
    return kardex.listar_movimientos(codigo=cod, tipo=tipo, id_empresa=None)


# ── Registro base + tipos ────────────────────────────────────────────────────
def test_registrar_y_tipos(db, fab):
    cod = fab.articulo(stock_total=10)
    fab.al_limpiar(lambda: _limpia(db, cod))
    assert kardex.registrar_movimiento(cod, "AJUSTE", 5, stock_anterior=10, stock_nuevo=15)
    assert kardex.registrar_movimiento(cod, "TIPO_INVALIDO", 1) is False    # tipo no soportado
    movs = _movs(db, cod)
    assert len(movs) == 1 and movs[0]["tipo_movimiento"] == "AJUSTE"
    assert movs[0]["stock_anterior"] == 10 and movs[0]["stock_nuevo"] == 15


# ── Venta → SALIDA_VENTA ─────────────────────────────────────────────────────
def test_venta_genera_salida(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = fab.articulo(stock_tienda=20)
    fab.al_limpiar(lambda: _limpia(db, cod))
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        vid = registrar_venta_con_items(
            [{"codigo_articulo": cod, "cantidad": 3, "precio_unitario": 2.0}])
    assert vid
    movs = _movs(db, cod, "SALIDA_VENTA")
    assert len(movs) == 1 and movs[0]["cantidad"] == 3
    assert str(movs[0]["id_documento"]) == str(vid)


def test_venta_simple_genera_salida(db, fab):
    from src.db.conexion import registrar_venta_con_items
    cod = fab.articulo(stock_tienda=20)
    fab.al_limpiar(lambda: _limpia(db, cod))
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        vid = registrar_venta_con_items([{"codigo_articulo": cod, "cantidad": 2,
                                          "precio_unitario": 1, "subtotal": 2}])
    assert vid
    assert len(_movs(db, cod, "SALIDA_VENTA")) == 1


# ── Devolución → DEVOLUCION ──────────────────────────────────────────────────
def test_devolucion_genera_movimiento(db, fab):
    from src.db.conexion import registrar_venta_con_items
    from src.services.tpv.refund_service import procesar_devolucion
    cod = fab.articulo(stock_tienda=20)
    fab.al_limpiar(lambda: _limpia(db, cod))
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        vid = registrar_venta_con_items(
            [{"codigo_articulo": cod, "cantidad": 4, "precio_unitario": 2.0}])
        ok, _msg, dev_id = procesar_devolucion(
            venta_id=vid,
            items_devolver=[{"codigo_articulo": cod, "nombre": "X", "cantidad": 2,
                             "precio_unitario": 2.0, "subtotal": 4.0, "modo_venta": "UNIDAD"}],
            forma_reembolso="efectivo", forma_pago_original="efectivo", empleado="ana",
            numero_caja=1, motivo="defecto")

    def _borra_dev():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM devolucion_items WHERE devolucion_id=%s", (dev_id,))
            cur.execute("DELETE FROM devoluciones WHERE id=%s", (dev_id,))
            conn.commit()
    fab.al_limpiar(_borra_dev)
    assert ok
    movs = _movs(db, cod, "DEVOLUCION")
    assert len(movs) == 1 and movs[0]["cantidad"] == 2
    assert str(movs[0]["id_documento"]) == str(dev_id)


# ── Ajuste → AJUSTE (anterior/nuevo/diferencia) ──────────────────────────────
def test_ajuste_manual_genera_movimiento(db, fab):
    from src.db.conexion import modificar_stock_completo
    cod = fab.articulo(stock_total=10, stock_tienda=0)
    fab.al_limpiar(lambda: _limpia(db, cod))
    assert modificar_stock_completo(cod, 0, 25, 0)          # total 10 → 25
    movs = _movs(db, cod, "AJUSTE")
    assert len(movs) == 1
    m = movs[0]
    assert m["stock_anterior"] == 10 and m["stock_nuevo"] == 25 and m["cantidad"] == 15


# ── Merma → MERMA ────────────────────────────────────────────────────────────
def test_merma_genera_movimiento(db, fab):
    from src.db.mermas import registrar_merma
    cod = fab.articulo(stock_total=10)
    fab.al_limpiar(lambda: _limpia(db, cod))
    fab.al_limpiar(lambda: _borra_mermas(db, cod))
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        assert registrar_merma(cod, 3, "rotura", columna_stock="Stock_total")
    movs = _movs(db, cod, "MERMA")
    assert len(movs) == 1 and movs[0]["cantidad"] == 3


def _borra_mermas(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM mermas WHERE codigo=%s", (cod,))
        conn.commit()


# ── Multiempresa ─────────────────────────────────────────────────────────────
def test_aislamiento_multiempresa(db, fab):
    cod = fab.articulo(stock_total=10)
    fab.al_limpiar(lambda: _limpia(db, cod))
    emp2 = fab.empresa("KARDEX B")
    kardex.registrar_movimiento(cod, "AJUSTE", 1, id_empresa=EMPRESA_DEFAULT_ID, id_tienda=None)
    kardex.registrar_movimiento(cod, "AJUSTE", 2, id_empresa=emp2, id_tienda=None)
    a = kardex.listar_movimientos(codigo=cod, id_empresa=EMPRESA_DEFAULT_ID)
    b = kardex.listar_movimientos(codigo=cod, id_empresa=emp2)
    assert len(a) == 1 and len(b) == 1
    assert a[0]["id_empresa"] == EMPRESA_DEFAULT_ID and b[0]["id_empresa"] == emp2


# ── Filtros del visor ────────────────────────────────────────────────────────
def test_filtros(db, fab):
    cod = fab.articulo(stock_total=50)
    fab.al_limpiar(lambda: _limpia(db, cod))
    ref = "DOC" + uuid.uuid4().hex[:6]
    kardex.registrar_movimiento(cod, "SALIDA_VENTA", 1, id_documento=ref, usuario="ana")
    kardex.registrar_movimiento(cod, "AJUSTE", 2, usuario="leo")
    assert len(kardex.listar_movimientos(codigo=cod, tipo="SALIDA_VENTA")) == 1
    assert len(kardex.listar_movimientos(codigo=cod, referencia=ref)) == 1
    assert len(kardex.listar_movimientos(codigo=cod, usuario="leo")) == 1
    assert len(kardex.listar_movimientos(codigo=cod)) == 2


# ── Historial completo + informes ────────────────────────────────────────────
def test_historial_e_informes(db, fab):
    cod = fab.articulo(stock_total=50)
    fab.al_limpiar(lambda: _limpia(db, cod))
    kardex.registrar_movimiento(cod, "ENTRADA_COMPRA", 10, usuario="ana")
    kardex.registrar_movimiento(cod, "SALIDA_VENTA", 3, usuario="ana")
    hist = kardex.historial_articulo(cod)
    assert [h["tipo_movimiento"] for h in hist] == ["ENTRADA_COMPRA", "SALIDA_VENTA"]  # cronológico asc
    assert len(kardex.movimientos_por_usuario("ana", codigo=cod)) == 2


# ── Best-effort: registro inválido no rompe ──────────────────────────────────
def test_best_effort_no_rompe(db):
    assert kardex.registrar_movimiento("", "AJUSTE", 1) is False        # sin código → no inserta
    assert kardex.registrar_movimiento(None, "SALIDA_VENTA", 1) is False


# ── GUI visor ────────────────────────────────────────────────────────────────
def test_visor_gui(db, fab):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    cod = fab.articulo(stock_total=10)
    fab.al_limpiar(lambda: _limpia(db, cod))
    kardex.registrar_movimiento(cod, "AJUSTE", 1, id_empresa=EMPRESA_DEFAULT_ID)
    with contexto_tenant(EMPRESA_DEFAULT_ID, None):
        from src.gui.kardex_visor import KardexVisorWindow
        w = KardexVisorWindow()
        w.f_codigo.setText(cod); w._buscar()
        assert w.tabla.rowCount() >= 1
        w.close()
