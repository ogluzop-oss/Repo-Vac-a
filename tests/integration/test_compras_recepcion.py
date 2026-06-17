"""E2.3 · Recepción contra pedido: parcial/total, actualización de stock y movimientos."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp, codigos):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        for c in codigos:
            cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (c,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _stock(db, codigo):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_total, Stock_central FROM articulos WHERE codigo=%s", (codigo,))
        return cur.fetchone()


def test_recepcion_total_actualiza_stock_y_estado(db, fab):
    from src.db import compras as C, proveedores as P
    emp = fab.empresa("REC TOTAL")
    cod = fab.articulo(id_empresa=emp, stock_total=0, stock_tienda=0)
    fab.al_limpiar(lambda: _borra(db, emp, [cod]))
    prov = P.crear_proveedor("PROV REC", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov,
                         lineas=[{"codigo": cod, "cantidad": 12, "precio_unitario": 1.0}],
                         id_empresa=emp)
    C.enviar_pedido(pid, emp)
    lin = C.obtener_pedido(pid, emp)["lineas"][0]
    res = C.recibir(pid, [{"id_linea": lin["id"], "cantidad": 12}], id_empresa=emp)
    assert res and res["estado_pedido"] == "RECIBIDO" and res["unidades"] == 12
    st = _stock(db, cod)
    assert st[0] == 12 and st[1] == 12          # Stock_total y Stock_central +12
    # Movimiento de entrada registrado.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT tipo_movimiento, cantidad FROM movimientos_stock "
                    "WHERE codigo_articulo=%s", (cod,))
        mv = cur.fetchone()
    assert mv[0] == "ENTRADA_COMPRA" and mv[1] == 12
    # cantidad_recibida actualizada.
    assert C.obtener_pedido(pid, emp)["lineas"][0]["cantidad_recibida"] == 12


def test_recepcion_parcial(db, fab):
    from src.db import compras as C, proveedores as P
    emp = fab.empresa("REC PARC")
    cod = fab.articulo(id_empresa=emp, stock_total=0)
    fab.al_limpiar(lambda: _borra(db, emp, [cod]))
    prov = P.crear_proveedor("PROV P", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov,
                         lineas=[{"codigo": cod, "cantidad": 10, "precio_unitario": 2.0}],
                         id_empresa=emp)
    C.enviar_pedido(pid, emp)
    lin = C.obtener_pedido(pid, emp)["lineas"][0]
    r1 = C.recibir(pid, [{"id_linea": lin["id"], "cantidad": 4}], id_empresa=emp)
    assert r1["estado_pedido"] == "PARCIAL"
    assert _stock(db, cod)[0] == 4
    # Segunda recepción completa el pedido.
    r2 = C.recibir(pid, [{"id_linea": lin["id"], "cantidad": 6}], id_empresa=emp)
    assert r2["estado_pedido"] == "RECIBIDO"
    assert _stock(db, cod)[0] == 10
    assert len(C.listar_recepciones(pid, emp)) == 2


def test_no_recibir_si_no_enviado(db, fab):
    from src.db import compras as C, proveedores as P
    emp = fab.empresa("REC NOENV")
    cod = fab.articulo(id_empresa=emp)
    fab.al_limpiar(lambda: _borra(db, emp, [cod]))
    prov = P.crear_proveedor("PROV NE", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov,
                         lineas=[{"codigo": cod, "cantidad": 5, "precio_unitario": 1.0}],
                         id_empresa=emp)
    # En BORRADOR no se puede recibir.
    assert C.recibir(pid, [{"codigo": cod, "cantidad": 5}], id_empresa=emp) is None
