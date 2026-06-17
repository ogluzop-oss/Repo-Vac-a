"""E2.5 · Facturas de proveedor: registro, vínculos y validación de importes."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_facturas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_registrar_factura_y_lineas(db, fab):
    from src.db import compras as C, proveedores as P
    emp = fab.empresa("FAC REG")
    fab.al_limpiar(lambda: _borra(db, emp))
    prov = P.crear_proveedor("PROV FAC", id_empresa=emp)
    fid = C.registrar_factura(id_proveedor=prov, numero_factura="F-2026/15",
                              lineas=[{"codigo": "ART001", "cantidad": 10, "precio_unitario": 2.0},
                                      {"codigo": "ART002", "cantidad": 5, "precio_unitario": 1.0}],
                              iva=5.25, id_empresa=emp)
    f = C.obtener_factura(fid, emp)
    assert f["numero_factura"] == "F-2026/15" and len(f["lineas"]) == 2
    assert float(f["base"]) == 25.0 and float(f["iva"]) == 5.25 and float(f["total"]) == 30.25
    assert f["estado"] == "registrada"


def test_validacion_contra_pedido(db, fab):
    from src.db import compras as C, proveedores as P
    emp = fab.empresa("FAC VAL")
    fab.al_limpiar(lambda: _borra(db, emp))
    prov = P.crear_proveedor("PROV V", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov,
                         lineas=[{"codigo": "ART001", "cantidad": 10, "precio_unitario": 2.0}],
                         id_empresa=emp)  # total 20.00
    # Factura que coincide con el pedido → validada.
    fid_ok = C.registrar_factura(id_proveedor=prov, id_pedido=pid, numero_factura="F-OK",
                                 lineas=[{"codigo": "ART001", "cantidad": 10, "precio_unitario": 2.0}],
                                 id_empresa=emp)
    r = C.validar_factura(fid_ok, id_empresa=emp)
    assert r["ok"] and r["estado"] == "validada" and r["diferencia"] == 0.0
    # Factura con diferencia → con_diferencias.
    fid_dif = C.registrar_factura(id_proveedor=prov, id_pedido=pid, numero_factura="F-DIF",
                                  lineas=[{"codigo": "ART001", "cantidad": 10, "precio_unitario": 2.5}],
                                  id_empresa=emp)
    r2 = C.validar_factura(fid_dif, id_empresa=emp)
    assert r2["ok"] is False and r2["estado"] == "con_diferencias" and r2["diferencia"] == 5.0


def test_listar_y_aislamiento(db, fab):
    from src.db import compras as C, proveedores as P
    a = fab.empresa("FAC A"); b = fab.empresa("FAC B")
    fab.al_limpiar(lambda: (_borra(db, a), _borra(db, b)))
    prov = P.crear_proveedor("PROV LA", id_empresa=a)
    fid = C.registrar_factura(id_proveedor=prov, numero_factura="F1", id_empresa=a,
                              lineas=[{"codigo": "X", "cantidad": 1, "precio_unitario": 1.0}])
    assert [f["id_factura"] for f in C.listar_facturas(a)] == [fid]
    assert C.listar_facturas(b) == []
    assert C.obtener_factura(fid, b) is None
