"""
Importador maestro — Fase 1 (universal). Lee CSV/Excel/JSON, auto-mapea cabeceras, valida (dry-run) y carga a
los motores oficiales: articulos (upsert por codigo) + familias (id_familia) + stock (Stock_total/stock_tienda)
+ kárdex. Multi-tenant e idempotente.
"""

import json

import pytest

from src.services import importacion as I
from src.services.importacion import motor as M


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(fab):
    for cod in ("IMP-A", "IMP-B", "IMP-C"):
        fab._borrar("articulos", "codigo", cod)
        fab._borrar("stock_tienda", "codigo_articulo", cod)
        fab._borrar("movimientos_stock", "codigo_articulo", cod)
    fab.al_limpiar(lambda: [fab._borrar("familias_producto", "nombre", n) for n in ("Bebidas", "Snacks")])


def _csv(tmp_path, contenido, nombre="cat.csv"):
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)


def _articulo(db, codigo):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT codigo, nombre, precio, Stock_total, id_familia, id_empresa FROM articulos "
                    "WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        return None if not r else dict(zip(
            ["codigo", "nombre", "precio", "stock", "id_familia", "id_empresa"], r))


def test_analizar_sugiere_mapeo(tmp_path):
    ruta = _csv(tmp_path, "codigo;nombre;precio;familia;stock\nIMP-A;Cola;1,50;Bebidas;10\n")
    plan = I.analizar(ruta)
    assert plan["ok"] and plan["formato"] == "csv" and plan["n_filas"] == 1
    m = plan["mapeo_sugerido"]
    assert m["codigo"] == "codigo" and m["precio"] == "precio" and m["stock"] == "stock"
    assert plan["faltan_requeridos"] == []


def test_carga_csv_crea_articulos_familia_y_stock(emp, db, tmp_path):
    ruta = _csv(tmp_path, "codigo;nombre;precio;familia;stock\n"
                          "IMP-A;Cola;1,50;Bebidas;10\nIMP-B;Agua;2.00;Bebidas;5\n")
    res = I.ejecutar(ruta, id_empresa=emp)
    assert res["ok"] and res["cargados"] == 2                # familias_creadas depende del estado global
    a = _articulo(db, "IMP-A")
    assert a and a["nombre"] == "Cola" and float(a["precio"]) == 1.50 and a["stock"] == 10
    assert a["id_empresa"] == emp and a["id_familia"] is not None       # familia vinculada
    # la familia se creó una sola vez y ambos artículos comparten id_familia
    assert _articulo(db, "IMP-B")["id_familia"] == a["id_familia"]


def test_cabeceras_alternativas_mapean(emp, db, tmp_path):
    ruta = _csv(tmp_path, "SKU,Nombre,PVP,Categoria,Existencias\nIMP-C,Barrita,0.99,Snacks,7\n")
    res = I.ejecutar(ruta, id_empresa=emp)
    assert res["ok"] and res["cargados"] == 1
    a = _articulo(db, "IMP-C")
    assert a["nombre"] == "Barrita" and a["stock"] == 7 and float(a["precio"]) == 0.99


def test_dry_run_no_escribe_y_clasifica(emp, db, tmp_path):
    ruta = _csv(tmp_path, "codigo;nombre;precio;stock\nIMP-A;Cola;1;3\n;SinCodigo;2;4\n")
    inf = I.simular(ruta, id_empresa=emp)
    assert inf["ok"]
    assert inf["resumen"]["validas"] == 1 and inf["resumen"]["con_error"] == 1
    assert inf["resumen"]["nuevos"] == 1
    assert _articulo(db, "IMP-A") is None                              # dry-run no escribió


def test_idempotente_reimportar_actualiza_no_duplica_ni_suma(emp, db, tmp_path):
    ruta = _csv(tmp_path, "codigo;nombre;precio;stock\nIMP-A;Cola;1,00;10\n")
    I.ejecutar(ruta, id_empresa=emp)
    ruta2 = _csv(tmp_path, "codigo;nombre;precio;stock\nIMP-A;Cola Zero;1,20;8\n", nombre="cat2.csv")
    res = I.ejecutar(ruta2, id_empresa=emp)
    assert res["ok"]
    a = _articulo(db, "IMP-A")
    assert a["nombre"] == "Cola Zero" and float(a["precio"]) == 1.20      # actualizado
    assert a["stock"] == 8                                                # FIJADO (no 10+8)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM articulos WHERE codigo='IMP-A'")
        assert cur.fetchone()[0] == 1                                     # sin duplicar


def test_json_tambien_se_importa(emp, db, tmp_path):
    ruta = tmp_path / "cat.json"
    ruta.write_text(json.dumps([{"codigo": "IMP-A", "nombre": "Cola", "precio": 1.5, "stock": 4}]),
                    encoding="utf-8")
    res = I.ejecutar(str(ruta), id_empresa=emp)
    assert res["ok"] and _articulo(db, "IMP-A")["stock"] == 4


def test_falta_codigo_obligatorio_aborta(emp, tmp_path):
    ruta = _csv(tmp_path, "nombre;precio\nCola;1\n")                       # sin columna de código
    res = I.ejecutar(ruta, id_empresa=emp)
    assert res["ok"] is False and "codigo" in res["error"].lower()
