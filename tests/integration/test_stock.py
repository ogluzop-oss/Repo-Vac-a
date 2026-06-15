"""Integración · descuento de stock canónico (bloqueo de fila, prioridad central→tienda)."""

import pytest

pytestmark = pytest.mark.db


def test_descontar_prioriza_total(db, fab):
    cod = fab.articulo(stock_total=5, stock_tienda=7)
    ok, desc_tot, desc_tie = db.descontar_stock(cod, 3)
    assert ok and desc_tot == 3 and desc_tie == 0       # sale primero del central
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_total, Stock_tienda FROM articulos WHERE codigo=%s", (cod,))
        assert cur.fetchone() == (2, 7)


def test_descontar_usa_tienda_si_falta_central(db, fab):
    cod = fab.articulo(stock_total=2, stock_tienda=5)
    ok, desc_tot, desc_tie = db.descontar_stock(cod, 4)
    assert ok and desc_tot == 2 and desc_tie == 2


def test_descontar_sin_stock_suficiente(db, fab):
    cod = fab.articulo(stock_total=1, stock_tienda=0)
    ok, _t, _ti = db.descontar_stock(cod, 5)
    assert ok is False
