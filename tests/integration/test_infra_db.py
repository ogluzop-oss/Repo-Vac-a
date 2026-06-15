"""Valida la infraestructura de pruebas de BD: creación de la BD de test,
esquema y factories con limpieza."""

import pytest

pytestmark = pytest.mark.db


def test_bd_es_de_pruebas(db):
    # Guard: jamás operamos sobre una BD que no termine en _test.
    assert db.DB_CONFIG["database"].endswith("_test")


def test_factory_empresa_y_articulo(db, fab):
    eid = fab.empresa("ACME TEST")
    cod = fab.articulo(id_empresa=eid, nombre="Demo", precio=3.5, stock_total=7)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre_empresa FROM empresas WHERE id_empresa=%s", (eid,))
        assert cur.fetchone()[0] == "ACME TEST"
        cur.execute("SELECT precio, Stock_total FROM articulos WHERE codigo=%s", (cod,))
        precio, stock = cur.fetchone()
        assert float(precio) == 3.5 and int(stock) == 7


def test_factory_limpia_al_terminar(db):
    # Tras el test anterior, sus filas deben haberse borrado (limpieza del fab).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM empresas WHERE nombre_empresa='ACME TEST'")
        assert cur.fetchone()[0] == 0
