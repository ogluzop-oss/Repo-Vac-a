"""
Variantes de producto por talla/color (edición Textil). Un modelo se despliega en SKUs (talla × color), cada
uno un artículo real con su stock/precio. Rejilla talla×color, búsqueda de variante e idempotencia.
"""

import pytest

from src.services import variantes as V

PADRE = "VAR-CAM"


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(db):
    def _borra():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM articulos WHERE codigo LIKE 'VAR-CAM%'")
            cur.execute("DELETE FROM producto_variantes WHERE codigo_padre=%s", (PADRE,))
            c.commit()
    _borra()          # estado limpio inmediato (evita restos de corridas previas)
    yield
    _borra()


def _crear_padre(db, emp, precio=12):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,precio) VALUES (%s,%s,'Camiseta',%s) "
                    "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), precio=VALUES(precio)", (PADRE, emp, precio))
        c.commit()


def test_crear_y_listar_variantes(emp, db):
    _crear_padre(db, emp, precio=12)
    res = V.crear_variantes(PADRE, tallas=["S", "M", "L"], colores=["ROJO", "AZUL"], id_empresa=emp)
    assert res["ok"] and res["variantes"] == 6
    vs = V.listar_variantes(PADRE, emp)
    assert len(vs) == 6
    assert all(v["precio"] == 12 for v in vs)                 # hereda precio del padre
    assert "VAR-CAM-S-ROJO" in {v["codigo_variante"] for v in vs}
    with db.obtener_conexion() as c, c.cursor() as cur:       # cada variante es un artículo real
        cur.execute("SELECT COUNT(*) FROM articulos WHERE codigo LIKE 'VAR-CAM-%%' AND id_empresa=%s", (emp,))
        assert cur.fetchone()[0] == 6


def test_matriz_y_stock_por_variante(emp, db):
    _crear_padre(db, emp)
    V.crear_variantes(PADRE, tallas=["S", "M", "L"], colores=["ROJO", "AZUL"], id_empresa=emp)
    vcod = V.buscar_variante(PADRE, "M", "AZUL", emp)
    assert vcod == "VAR-CAM-M-AZUL"
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("UPDATE articulos SET Stock_total=7 WHERE codigo=%s AND id_empresa=%s", (vcod, emp))
        c.commit()
    m = V.matriz(PADRE, emp)
    assert set(m["tallas"]) == {"S", "M", "L"} and set(m["colores"]) == {"ROJO", "AZUL"}
    assert len(m["celdas"]) == 6
    celda = next(x for x in m["celdas"] if x["talla"] == "M" and x["color"] == "AZUL")
    assert celda["stock"] == 7 and celda["codigo"] == vcod
    assert m["stock_total"] == 7


def test_idempotente(emp, db):
    _crear_padre(db, emp)
    V.crear_variantes(PADRE, tallas=["S", "M"], colores=["ROJO"], id_empresa=emp)
    V.crear_variantes(PADRE, tallas=["S", "M"], colores=["ROJO"], id_empresa=emp)   # segunda pasada
    assert len(V.listar_variantes(PADRE, emp)) == 2                                 # sin duplicar
