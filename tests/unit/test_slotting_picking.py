"""
Tests de SLOTTING inteligente y OPTIMIZACIÓN DE RUTAS DE PICKING (WMS, sin coste externo).

Slotting: clasificación ABC por rotación (el top siempre A, sin rotación C), análisis rotación↔ubicación y
recomendación de intercambio (A/B en zona lejana ↔ C en zona accesible) + aplicación.
Rutas: parseo de ubicación y recorrido serpentín (minimiza desplazamiento).
"""

import pytest

from src.services.inventario import picking_ruta as PR
from src.services.inventario import slotting as SL


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


# ── Rutas de picking ──────────────────────────────────────────────────────────
def test_parsear_ubicacion():
    assert PR.parsear_ubicacion("P3-E12-B4") == (3, 12, 4)
    assert PR.parsear_ubicacion("1-2-3") == (1, 2, 3)
    assert PR.parsear_ubicacion("") == (9999, 9999, 9999)


def test_ruta_serpentin():
    lineas = [{"ubicacion": "3-1-1"}, {"ubicacion": "1-2-1"}, {"ubicacion": "1-1-1"},
              {"ubicacion": "2-1-1"}]
    ordenadas, met = PR.optimizar_ruta(lineas)
    # pasillo asc; en el pasillo 1 (impar) la estantería baja (E2 antes que E1); luego 2 y 3
    assert [o["ubicacion"] for o in ordenadas] == ["1-2-1", "1-1-1", "2-1-1", "3-1-1"]
    assert [o["orden"] for o in ordenadas] == [1, 2, 3, 4]
    assert met["pasillos"] == 3 and met["lineas"] == 4


# ── Slotting ──────────────────────────────────────────────────────────────────
def test_clasificar_abc():
    clase = SL.clasificar_abc({"x": 80, "y": 15, "z": 5, "w": 0})
    assert clase["x"] == "A" and clase["y"] == "B" and clase["z"] == "C" and clase["w"] == "C"


def _ubicar(fab, emp, db, codigo, pasillo, est, balda):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO ubicaciones (codigo_articulo,pasillo,estanteria,balda,id_empresa) "
                    "VALUES (%s,%s,%s,%s,%s)", (codigo, pasillo, est, balda, emp))
    fab._borrar("ubicaciones", "codigo_articulo", codigo)


def _vender(fab, emp, db, codigo, cantidad):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha,codigo,cantidad,total,id_empresa) VALUES (NOW(),%s,%s,%s,%s)",
                    (codigo, cantidad, cantidad, emp))
    fab._borrar("ventas", "codigo", codigo)


def test_analizar_y_aplicar_intercambio(fab, db):
    emp = fab.empresa("EMP SLOT AISLADA")   # empresa nueva → sin ubicaciones acumuladas de otros tests
    a1 = fab.articulo(nombre="Rapido", id_empresa=emp)
    c1 = fab.articulo(nombre="Lento", id_empresa=emp)
    _ubicar(fab, emp, db, a1, "9", "9", "9")   # producto de alta rotación en zona lejana
    _ubicar(fab, emp, db, c1, "1", "1", "1")   # producto sin rotación en zona accesible (golden)
    _vender(fab, emp, db, a1, 100)

    res = SL.analizar(emp)
    assert res["abc"]["A"] >= 1
    rec = [r for r in res["recomendaciones"] if r["codigo"] == a1]
    assert rec, "debe recomendar mover el producto de alta rotación"
    r = rec[0]
    assert r["ubicacion_actual"] == "9-9-9" and r["codigo_intercambio"] == c1
    # aplicar el intercambio → a1 pasa a la ubicación accesible
    assert SL.aplicar_intercambio(r["id_ubicacion"], r["id_ubicacion_sugerida"], id_empresa=emp)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT codigo_articulo FROM ubicaciones WHERE id=%s", (r["id_ubicacion_sugerida"],))
        assert cur.fetchone()[0] == a1


def test_analizar_sin_ubicaciones(fab, emp):
    # empresa nueva sin ubicaciones ocupadas propias → no rompe
    otra = fab.empresa("EMP SLOT VACIA")
    res = SL.analizar(otra)
    assert res["recomendaciones"] == [] and res["abc"] == {"A": 0, "B": 0, "C": 0}
