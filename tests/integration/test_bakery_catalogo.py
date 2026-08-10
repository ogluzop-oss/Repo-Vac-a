"""
Catálogo por defecto de la edición BAKERY: `verticales.aplicar_datos_por_defecto` siembra las 3 familias
(Dulce/Salado/Bebidas) y sus productos por defecto de forma IDEMPOTENTE y NO destructiva (INSERT IGNORE:
no pisa precios/nombres editados). Los productos quedan ligados a su familia (los lee el TPV bakery).
"""

import pytest

pytestmark = pytest.mark.db

from src.services import verticales as V
from src.db import familias as F


@pytest.fixture
def emp(fab):
    return fab.empresa("BAKERY CAT")


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    def _b():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM articulos WHERE id_empresa=%s AND codigo LIKE 'BK-%%'", (emp,))
            cur.execute("DELETE FROM familias_producto WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
            c.commit()
    yield
    _b()


def test_siembra_familias_y_productos_bakery(db, emp):
    r = V.aplicar_datos_por_defecto(emp, vertical="BAKERY")
    assert r["ok"] and r["familias_creadas"] == 3
    assert r["productos_creados"] > 20                      # se siembran las 3 familias con productos
    fams = {str(f["nombre"]).lower(): f["id"] for f in F.listar_familias(emp, solo_activas=False)}
    assert set(fams) == {"dulce", "salado", "bebidas"}
    for fam in ("dulce", "salado", "bebidas"):
        arts = F.articulos_de_familia(fams[fam], emp)
        assert len(arts) >= 5                               # cada familia trae varios productos
        assert all(a["codigo"].startswith("BK-") and float(a["precio"]) > 0 for a in arts)
        assert all((a.get("emoji") or "").strip() for a in arts)   # cada producto trae emoji


def test_siembra_idempotente_y_no_destructiva(db, emp):
    V.aplicar_datos_por_defecto(emp, vertical="BAKERY")
    # El comercio edita el precio de un producto sembrado.
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("UPDATE articulos SET precio=9.99 WHERE id_empresa=%s AND codigo='BK-DUL01'", (emp,))
        c.commit()
    r2 = V.aplicar_datos_por_defecto(emp, vertical="BAKERY")   # re-siembra
    assert r2["productos_creados"] == 0                         # no crea duplicados
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT precio FROM articulos WHERE id_empresa=%s AND codigo='BK-DUL01'", (emp,))
        row = cur.fetchone()
        precio = float(row[0] if not isinstance(row, dict) else list(row.values())[0])
    assert precio == 9.99                                       # NO se pisa la edición del comercio


def test_otras_ediciones_no_siembran_productos(db, emp):
    r = V.aplicar_datos_por_defecto(emp, vertical="RETAIL")
    assert r.get("productos_creados", 0) == 0


def test_gestion_familia_listar_asignar_precio(db, emp):
    """Flujo del gestor de productos del TPV bakery: listar todos con su familia + reasignar familia y
    precio (lo que hace `_GestionProductosFamiliaDialog` a nivel de servicio)."""
    from src.db import articulos as A
    V.aplicar_datos_por_defecto(emp, vertical="BAKERY")
    fams = {str(f["nombre"]).lower(): f["id"] for f in F.listar_familias(emp, solo_activas=False)}
    # listar_articulos_con_familia devuelve todos con su familia asignada
    todos = F.listar_articulos_con_familia(emp)
    croissant = next(a for a in todos if a["codigo"] == "BK-DUL01")
    assert croissant["id_familia"] == fams["dulce"] and croissant["familia"] == "Dulce"
    # reasignar a Salado + cambiar precio (como hace el gestor)
    assert A.actualizar_precio("BK-DUL01", 1.99, id_empresa=emp)
    assert F.asignar_familia("BK-DUL01", fams["salado"], id_empresa=emp)
    de_nuevo = {a["codigo"]: a for a in F.listar_articulos_con_familia(emp)}["BK-DUL01"]
    assert de_nuevo["familia"] == "Salado" and float(de_nuevo["precio"]) == 1.99
