"""
Tests de FAMILIAS DE PRODUCTO (migración 0167).

Cubre: CRUD de familias, asignación GLOBAL artículo↔familia (articulos.id_familia), que eliminar una
familia DESVINCULA sus artículos (sin borrarlos), y el AISLAMIENTO multiempresa (una familia de la empresa
A nunca es visible ni asignable desde la empresa B).
"""

import pytest

from src.db import familias as F


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _nueva_familia(fab, emp, nombre="Bebidas", **kw):
    fid = F.crear_familia(nombre, id_empresa=emp, **kw)
    fab._borrar("familias_producto", "id", fid)
    return fid


def test_crud_familia(fab, emp):
    fid = _nueva_familia(fab, emp, "Lácteos", descripcion="Leche y derivados", color="#22D3EE")
    assert fid
    fam = F.obtener_familia(fid, id_empresa=emp)
    assert fam and fam["nombre"] == "Lácteos" and fam["descripcion"] == "Leche y derivados"
    assert any(f["id"] == fid for f in F.listar_familias(id_empresa=emp))
    assert F.actualizar_familia(fid, id_empresa=emp, nombre="Lácteos y quesos")
    assert F.obtener_familia(fid, id_empresa=emp)["nombre"] == "Lácteos y quesos"
    assert F.eliminar_familia(fid, id_empresa=emp)
    assert F.obtener_familia(fid, id_empresa=emp) is None


def test_asignacion_global(fab, emp):
    fid = _nueva_familia(fab, emp, "Limpieza")
    cod = fab.articulo(nombre="Detergente", id_empresa=emp)
    assert F.asignar_familia(cod, fid, id_empresa=emp)
    fam = F.familia_de_articulo(cod, id_empresa=emp)
    assert fam and fam["id"] == fid
    assert F.contar_por_familia(id_empresa=emp).get(fid) == 1
    assert any(a["codigo"] == cod for a in F.articulos_de_familia(fid, id_empresa=emp))
    # Renombrar NO rompe el vínculo (va por id).
    F.actualizar_familia(fid, id_empresa=emp, nombre="Higiene")
    assert F.familia_de_articulo(cod, id_empresa=emp)["id"] == fid
    # Desasignar (None).
    assert F.asignar_familia(cod, None, id_empresa=emp)
    assert F.familia_de_articulo(cod, id_empresa=emp) is None


def test_eliminar_desvincula_sin_borrar_articulo(fab, emp, db):
    fid = _nueva_familia(fab, emp, "Congelados")
    cod = fab.articulo(nombre="Guisantes", id_empresa=emp)
    F.asignar_familia(cod, fid, id_empresa=emp)
    assert F.eliminar_familia(fid, id_empresa=emp)
    # El artículo sigue existiendo pero sin familia.
    assert F.familia_de_articulo(cod, id_empresa=emp) is None
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT id_familia FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        fila = cur.fetchone()
    assert fila is not None and fila[0] is None


def test_aislamiento_multiempresa(fab, emp):
    otra = fab.empresa("EMPRESA FAMILIAS B")
    fid_a = _nueva_familia(fab, emp, "Solo A")
    fid_b = _nueva_familia(fab, otra, "Solo B")
    # Cada empresa ve solo lo suyo.
    ids_a = {f["id"] for f in F.listar_familias(id_empresa=emp)}
    ids_b = {f["id"] for f in F.listar_familias(id_empresa=otra)}
    assert fid_a in ids_a and fid_a not in ids_b
    assert fid_b in ids_b and fid_b not in ids_a
    # No se puede leer una familia de otra empresa.
    assert F.obtener_familia(fid_b, id_empresa=emp) is None
    # Asignar con empresa que no es dueña del artículo no afecta.
    cod = fab.articulo(nombre="Art A", id_empresa=emp)
    assert F.asignar_familia(cod, fid_a, id_empresa=otra)  # ejecuta pero no matchea (empresa distinta)
    assert F.familia_de_articulo(cod, id_empresa=emp) is None


# ── Fase 2: filtrado, operaciones masivas y analítica ─────────────────────────
def test_articulos_filtrados(fab, emp):
    fid = _nueva_familia(fab, emp, "Snacks F2")
    c1 = fab.articulo(nombre="Patatas Fritas", id_empresa=emp)
    c2 = fab.articulo(nombre="Nachos Queso", id_empresa=emp)
    fab.articulo(nombre="Fuera De Familia", id_empresa=emp)
    F.asignar_familia(c1, fid, id_empresa=emp)
    F.asignar_familia(c2, fid, id_empresa=emp)
    r = F.articulos_filtrados(id_familia=fid, id_empresa=emp)
    assert {row[0] for row in r} == {c1, c2}
    # texto + familia
    r2 = F.articulos_filtrados("Nachos", id_familia=fid, id_empresa=emp)
    assert len(r2) == 1 and r2[0][0] == c2
    # id_familia=0 → sin familia (no debe incluir los asignados)
    sin = {row[0] for row in F.articulos_filtrados(id_familia=0, id_empresa=emp)}
    assert c1 not in sin and c2 not in sin


def test_cambiar_precio_masivo(fab, emp, db):
    fid = _nueva_familia(fab, emp, "Precios F2")
    c1 = fab.articulo(nombre="P1", id_empresa=emp, precio=2.0)
    c2 = fab.articulo(nombre="P2", id_empresa=emp, precio=4.0)
    for c in (c1, c2):
        F.asignar_familia(c, fid, id_empresa=emp)

    def precio(c):
        with db.obtener_conexion() as cn, cn.cursor() as cur:
            cur.execute("SELECT precio FROM articulos WHERE codigo=%s", (c,))
            return float(cur.fetchone()[0])

    def iva(c):
        with db.obtener_conexion() as cn, cn.cursor() as cur:
            cur.execute("SELECT iva FROM articulos WHERE codigo=%s", (c,))
            return float(cur.fetchone()[0])

    assert F.cambiar_precio_masivo(fid, "pct", 10, id_empresa=emp) == 2
    assert abs(precio(c1) - 2.20) < 0.001 and abs(precio(c2) - 4.40) < 0.001
    assert F.cambiar_precio_masivo(fid, "fijo", 9.99, id_empresa=emp) == 2
    assert abs(precio(c1) - 9.99) < 0.001
    assert F.cambiar_precio_masivo(fid, "iva", 4, id_empresa=emp) == 2
    assert abs(iva(c2) - 4) < 0.001
    # modo inválido no afecta
    assert F.cambiar_precio_masivo(fid, "xxx", 1, id_empresa=emp) == 0


def test_ventas_por_familia(fab, emp, db):
    fid = _nueva_familia(fab, emp, "Ventas F2")
    cod = fab.articulo(nombre="Vendido", id_empresa=emp)
    F.asignar_familia(cod, fid, id_empresa=emp)
    with db.obtener_conexion() as cn, cn.cursor() as cur:
        cur.execute("INSERT INTO ventas (fecha, codigo, cantidad, total, id_empresa) "
                    "VALUES (NOW(), %s, %s, %s, %s)", (cod, 3, 29.97, emp))
        vid = cur.lastrowid
    try:
        vf = F.ventas_por_familia(id_empresa=emp, dias=7)
        fila = [x for x in vf if x["id_familia"] == fid]
        assert fila and int(fila[0]["unidades"]) == 3 and abs(float(fila[0]["importe"]) - 29.97) < 0.01
    finally:
        with db.obtener_conexion() as cn, cn.cursor() as cur:
            cur.execute("DELETE FROM ventas WHERE id=%s", (vid,))
