"""
Recetas y dispensación (edición Pharmacy). Crear receta, dispensar (descuenta stock por el motor OFICIAL de
salida → kárdex), dispensación PARCIAL si falta stock, y anulación. Multi-tenant.
"""

import pytest

from src.services import recetas as R

MED_A, MED_B = "RX-MED-A", "RX-MED-B"


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(db):
    def _borra():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM recetas_lineas WHERE id_receta IN (SELECT id FROM recetas WHERE "
                        "paciente LIKE 'RXTEST%')")
            cur.execute("DELETE FROM recetas WHERE paciente LIKE 'RXTEST%'")
            for cod in (MED_A, MED_B):
                cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
                cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (cod,))
            c.commit()
    _borra()
    yield
    _borra()


def _med(db, emp, cod, stock):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total) "
                    "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE Stock_tienda=VALUES(Stock_tienda), "
                    "Stock_total=VALUES(Stock_total)", (cod, emp, "Medicamento " + cod, stock, stock))
        c.commit()


def _stock(db, emp, cod):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        return int(cur.fetchone()[0] or 0)


def test_crear_receta(emp):
    rid = R.crear_receta("RXTEST Juan", [{"codigo": MED_A, "cantidad": 2, "posologia": "1/8h"}], id_empresa=emp)
    assert rid
    rec = R.obtener_receta(rid, id_empresa=emp)
    assert rec["estado"] == "PENDIENTE" and len(rec["lineas"]) == 1
    assert rec["lineas"][0]["codigo_articulo"] == MED_A and rec["lineas"][0]["cantidad"] == 2


def test_dispensar_descuenta_stock(emp, db):
    _med(db, emp, MED_A, 10)
    rid = R.crear_receta("RXTEST Ana", [{"codigo": MED_A, "cantidad": 2}], id_empresa=emp)
    res = R.dispensar(rid, id_empresa=emp)
    assert res["ok"] and res["estado"] == "DISPENSADA" and res["dispensadas"] == 2
    assert _stock(db, emp, MED_A) == 8                       # stock descontado por el motor oficial
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE codigo_articulo=%s", (MED_A,))
        assert cur.fetchone()[0] >= 1                        # kárdex de salida


def test_dispensar_parcial_si_falta_stock(emp, db):
    _med(db, emp, MED_B, 1)
    rid = R.crear_receta("RXTEST Luis", [{"codigo": MED_B, "cantidad": 5}], id_empresa=emp)
    res = R.dispensar(rid, id_empresa=emp)
    assert res["ok"] and res["estado"] == "PARCIAL" and res["dispensadas"] == 1
    assert _stock(db, emp, MED_B) == 0
    assert R.obtener_receta(rid, id_empresa=emp)["lineas"][0]["dispensado"] == 1


def test_anular(emp):
    rid = R.crear_receta("RXTEST Eva", [{"codigo": MED_A, "cantidad": 1}], id_empresa=emp)
    assert R.anular(rid, id_empresa=emp)
    assert R.obtener_receta(rid, id_empresa=emp)["estado"] == "ANULADA"
    assert R.dispensar(rid, id_empresa=emp)["ok"] is False   # anulada no se dispensa
