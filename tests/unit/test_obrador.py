"""
Obrador / producción diaria (edición Bakery). Producir un terminado consume sus ingredientes (BOM) por la salida
oficial y da de alta el stock vendible (+kárdex). Parte del día. Reutiliza los motores de stock generales.
"""

import pytest

from src.services import obrador
from src.services.mrp import bom


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(db):
    def _borra():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM obrador_partes_lineas WHERE id_parte IN (SELECT id FROM obrador_partes "
                        "WHERE responsable='OBRTEST')")
            cur.execute("DELETE FROM obrador_partes WHERE responsable='OBRTEST'")
            cur.execute("DELETE FROM bom_lineas WHERE id_bom IN (SELECT id FROM bom WHERE articulo_final='OBR-PAN')")
            cur.execute("DELETE FROM bom WHERE articulo_final='OBR-PAN'")
            for cod in ("OBR-PAN", "OBR-HARINA"):
                cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
                cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (cod,))
            c.commit()
    _borra()
    yield
    _borra()


def _setup(db, emp):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total) "
                    "VALUES ('OBR-PAN',%s,'Pan',0,0) ON DUPLICATE KEY UPDATE Stock_tienda=0,Stock_total=0", (emp,))
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total) "
                    "VALUES ('OBR-HARINA',%s,'Harina',100,100) ON DUPLICATE KEY UPDATE Stock_tienda=100,"
                    "Stock_total=100", (emp,))
        c.commit()
    bom.crear_bom("OBR-PAN", lineas=[{"componente": "OBR-HARINA", "cantidad": 2}], id_empresa=emp)


def _stock(db, emp, cod):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        return int(cur.fetchone()[0] or 0)


def test_producir_consume_ingredientes_y_da_alta_terminado(emp, db):
    _setup(db, emp)
    r = obrador.producir("OBR-PAN", 5, id_empresa=emp)
    assert r["ok"] and r["producido"] == 5
    assert _stock(db, emp, "OBR-PAN") == 5          # terminado vendible
    assert _stock(db, emp, "OBR-HARINA") == 90      # ingrediente consumido (5×2)
    assert any(c["componente"] == "OBR-HARINA" and c["cantidad"] == 10 for c in r["consumidos"])
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE codigo_articulo='OBR-PAN' AND "
                    "tipo_movimiento='ENTRADA_PRODUCCION'")
        assert cur.fetchone()[0] >= 1               # kárdex de producción


def test_parte_diario(emp, db):
    _setup(db, emp)
    res = obrador.registrar_produccion_diaria([{"codigo": "OBR-PAN", "cantidad": 3}],
                                              responsable="OBRTEST", id_empresa=emp)
    assert res["ok"] and res["producidos"] == 3
    assert _stock(db, emp, "OBR-PAN") == 3 and _stock(db, emp, "OBR-HARINA") == 94
    parte = obrador.obtener_parte(res["parte"], id_empresa=emp)
    assert parte["lineas"][0]["codigo_articulo"] == "OBR-PAN" and parte["lineas"][0]["cantidad"] == 3


def test_consumo_materia_prima_va_a_contabilidad(db, fab):
    """La materia prima consumida en el obrador se lleva AUTOMÁTICAMENTE a contabilidad como gasto de
    materias primas (Debe 601 / Haber 300) por su coste."""
    from src.services.contabilidad import asientos as A
    from src.services.contabilidad import cuentas as K
    emp2 = fab.empresa("OBR CONTAB")

    def _limpia_contab():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM contab_asientos WHERE id_empresa=%s", (emp2,))
            cur.execute("DELETE FROM contab_cuentas WHERE id_empresa=%s", (emp2,))
            cur.execute("DELETE FROM contab_ejercicios WHERE id_empresa=%s", (emp2,))
            cur.execute("DELETE FROM contab_config WHERE id_empresa=%s", (emp2,))
            cur.execute("DELETE FROM articulos WHERE codigo IN ('OBR-PAN','OBR-HARINA') AND id_empresa=%s", (emp2,))
            c.commit()
    _limpia_contab()
    fab.al_limpiar(_limpia_contab)
    K.activar(emp2, 2026)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total) "
                    "VALUES ('OBR-PAN',%s,'Pan',0,0)", (emp2,))
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total,coste_medio) "
                    "VALUES ('OBR-HARINA',%s,'Harina',100,100,2.0)", (emp2,))
        c.commit()
    bom.crear_bom("OBR-PAN", lineas=[{"componente": "OBR-HARINA", "cantidad": 2}], id_empresa=emp2)

    r = obrador.producir("OBR-PAN", 5, id_empresa=emp2)     # consume 10 harina × 2.0 = 20.0
    assert r["ok"] and r["coste_materia_prima"] == 20.0
    consumo = [a for a in A.listar_diario(emp2, anio=2026) if a.get("origen") == "consumo_mp"]
    assert consumo, "no se generó el asiento de consumo de materia prima"
    apuntes = A.obtener_asiento(consumo[0]["id"], emp2)["apuntes"]
    debe_601 = sum(float(x["debe"] or 0) for x in apuntes if str(x["codigo_cuenta"]).startswith("601"))
    haber_300 = sum(float(x["haber"] or 0) for x in apuntes if str(x["codigo_cuenta"]).startswith("300"))
    assert debe_601 == 20.0 and haber_300 == 20.0


def test_producir_sin_bom_solo_da_alta(emp, db):
    with db.obtener_conexion() as c, c.cursor() as cur:      # producto sin BOM (no consume nada)
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total) "
                    "VALUES ('OBR-PAN',%s,'Pan',0,0) ON DUPLICATE KEY UPDATE Stock_tienda=0,Stock_total=0", (emp,))
        c.commit()
    r = obrador.producir("OBR-PAN", 4, id_empresa=emp)
    assert r["ok"] and r["consumidos"] == [] and _stock(db, emp, "OBR-PAN") == 4
