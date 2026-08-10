"""
Fase 5: multi-entidad (clientes/proveedores, idempotente por NIF), conector directo GATED por plan
(api.access) y auditoría/reanudación (import_trabajos con estado).
"""

import pytest

from src.services import importacion as I


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpiar(fab):
    for nif in ("B11111111", "B22222222"):
        fab._borrar("clientes", "nif", nif)
    fab._borrar("proveedores", "cif_nif", "A11111111")
    for cod in ("F5-API",):
        fab._borrar("articulos", "codigo", cod)
        fab._borrar("stock_tienda", "codigo_articulo", cod)
        fab._borrar("movimientos_stock", "codigo_articulo", cod)


def _csv(tmp_path, contenido, nombre="f.csv"):
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)


def _cli(db, nif):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT nombre, email FROM clientes WHERE nif=%s", (nif,))
        r = cur.fetchone()
        return None if not r else {"nombre": r[0], "email": r[1]}


def test_importar_clientes(emp, db, tmp_path):
    ruta = _csv(tmp_path, "nombre;nif;email;telefono\n"
                          "Cliente Uno;B11111111;uno@x.com;600111222\n"
                          "Cliente Dos;B22222222;dos@x.com;600333444\n")
    res = I.ejecutar(ruta, entidad=I.CLIENTES, id_empresa=emp)
    assert res["ok"] and res["cargados"] == 2 and res["creados"] == 2
    assert _cli(db, "B11111111")["nombre"] == "Cliente Uno"


def test_clientes_idempotente_por_nif(emp, db, tmp_path):
    _csv1 = _csv(tmp_path, "nombre;nif;email\nCliente Uno;B11111111;uno@x.com\n")
    I.ejecutar(_csv1, entidad=I.CLIENTES, id_empresa=emp)
    _csv2 = _csv(tmp_path, "nombre;nif;email\nCliente Uno;B11111111;nuevo@x.com\n", nombre="f2.csv")
    res = I.ejecutar(_csv2, entidad=I.CLIENTES, id_empresa=emp)
    assert res["actualizados"] == 1 and res["creados"] == 0        # dedupe por NIF
    assert _cli(db, "B11111111")["email"] == "nuevo@x.com"          # actualizado
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM clientes WHERE nif='B11111111'")
        assert cur.fetchone()[0] == 1                               # sin duplicar


def test_importar_proveedores(emp, db, tmp_path):
    ruta = _csv(tmp_path, "razon_social;cif;email\nProv Uno;A11111111;prov@x.com\n")
    res = I.ejecutar(ruta, entidad=I.PROVEEDORES, id_empresa=emp)
    assert res["ok"] and res["cargados"] == 1
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT razon_social FROM proveedores WHERE cif_nif='A11111111'")
        assert cur.fetchone()[0] == "Prov Uno"


def test_simular_clientes(emp, tmp_path):
    ruta = _csv(tmp_path, "nombre;nif\nCliente Uno;B11111111\n;SinNombre\n")
    inf = I.simular(ruta, entidad=I.CLIENTES, id_empresa=emp)
    assert inf["ok"] and inf["resumen"]["validas"] == 1 and inf["resumen"]["con_error"] == 1


def test_conector_directo_gated_por_plan(emp, monkeypatch):
    import src.services.saas.entitlements as ent
    monkeypatch.setattr(ent, "can", lambda cap, id_empresa=None: False)   # simula plan sin api.access
    res = I.importar_desde_api("http://origen", id_empresa=emp,
                               fetch=lambda u: [{"codigo": "X", "nombre": "Y"}])
    assert res["ok"] is False and "plan" in res["error"].lower()


def test_conector_api_carga_cuando_plan_lo_permite(emp, db):
    # empresa de test sin licencia → plan PLUS (acceso total) → el conector procede
    res = I.importar_desde_api("http://origen", id_empresa=emp,
                               fetch=lambda u: {"data": [{"codigo": "F5-API", "nombre": "ApiX", "stock": 2}]})
    assert res["ok"] and res["cargados"] == 1
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT Stock_total FROM articulos WHERE codigo='F5-API'")
        assert cur.fetchone()[0] == 2


def test_trabajos_recientes_auditados(emp, tmp_path):
    ruta = _csv(tmp_path, "nombre;nif\nCliente Uno;B11111111\n")
    I.ejecutar(ruta, entidad=I.CLIENTES, id_empresa=emp)
    tj = I.trabajos_recientes(emp, limite=5)
    assert tj and tj[0]["estado"] == "completado" and tj[0]["entidad"] == "clientes"
