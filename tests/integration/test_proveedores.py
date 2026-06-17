"""E2.1 · Proveedores: CRUD + contactos + direcciones + aislamiento por empresa."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))   # cascada contactos/direcciones
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_crud_proveedor(db, fab):
    from src.db import proveedores as P
    emp = fab.empresa("PROV CRUD")
    fab.al_limpiar(lambda: _borra(db, emp))
    pid = P.crear_proveedor("ACME SUMINISTROS SL", cif_nif="B12345678",
                            email="ventas@acme.test", id_empresa=emp)
    assert pid
    p = P.obtener_proveedor(pid, emp)
    assert p["razon_social"] == "ACME SUMINISTROS SL" and p["estado"] == "activo"
    assert P.actualizar_proveedor(pid, id_empresa=emp, telefono="600111222",
                                  nombre_comercial="ACME")
    assert P.obtener_proveedor(pid, emp)["nombre_comercial"] == "ACME"
    assert [x["id_proveedor"] for x in P.listar_proveedores(emp)] == [pid]
    assert P.listar_proveedores(emp, texto="acme")
    # Baja lógica.
    assert P.eliminar_proveedor(pid, emp)
    assert P.obtener_proveedor(pid, emp)["estado"] == "inactivo"
    assert P.listar_proveedores(emp, estado="activo") == []


def test_contactos_y_direcciones(db, fab):
    from src.db import proveedores as P
    emp = fab.empresa("PROV CONT")
    fab.al_limpiar(lambda: _borra(db, emp))
    pid = P.crear_proveedor("DISTRI SA", id_empresa=emp)
    cid = P.agregar_contacto(pid, "Ana López", cargo="Comercial", email="ana@distri.test")
    did = P.agregar_direccion(pid, direccion="Pol. Ind. 5", tipo="almacen",
                              cp="28906", municipio="Getafe", provincia="Madrid")
    assert cid and did
    assert P.listar_contactos(pid)[0]["nombre"] == "Ana López"
    assert P.listar_direcciones(pid)[0]["tipo"] == "almacen"


def test_aislamiento_por_empresa(db, fab):
    from src.db import proveedores as P
    a = fab.empresa("PROV A"); b = fab.empresa("PROV B")
    fab.al_limpiar(lambda: (_borra(db, a), _borra(db, b)))
    pa = P.crear_proveedor("SOLO A", id_empresa=a)
    assert P.obtener_proveedor(pa, b) is None         # B no ve el proveedor de A
    assert P.listar_proveedores(b) == []
    assert P.actualizar_proveedor(pa, id_empresa=b, telefono="x") is False
