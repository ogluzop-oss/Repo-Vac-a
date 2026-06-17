"""E2.4 · Costes de compra: último/actual/medio ponderado tras recepción."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo=%s", (cod,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _recepcion(emp, cod, cantidad, precio):
    from src.db import compras as C, proveedores as P
    prov = P.crear_proveedor("PROV COSTE", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov,
                         lineas=[{"codigo": cod, "cantidad": cantidad, "precio_unitario": precio}],
                         id_empresa=emp)
    C.enviar_pedido(pid, emp)
    lin = C.obtener_pedido(pid, emp)["lineas"][0]
    C.recibir(pid, [{"id_linea": lin["id"], "cantidad": cantidad}], id_empresa=emp)


def test_costes_se_actualizan_y_promedian(db, fab):
    from src.db import compras as C
    emp = fab.empresa("COSTE 1")
    cod = fab.articulo(id_empresa=emp, stock_total=0)
    fab.al_limpiar(lambda: _borra(db, emp, cod))
    # 1ª compra: 10 uds a 2.00 → medio 2.00, último 2.00.
    _recepcion(emp, cod, 10, 2.00)
    c = C.obtener_costes(cod)
    assert c["ultimo_coste"] == 2.00 and c["coste_actual"] == 2.00 and c["coste_medio"] == 2.00
    # 2ª compra: 10 uds a 4.00 → último 4.00; medio ponderado = (2*10+4*10)/20 = 3.00.
    _recepcion(emp, cod, 10, 4.00)
    c = C.obtener_costes(cod)
    assert c["ultimo_coste"] == 4.00 and c["coste_medio"] == 3.00


def test_costes_no_rompen_catalogo(db, fab):
    """El PVP (precio) no se altera al actualizar costes."""
    from src.db import compras as C
    emp = fab.empresa("COSTE 2")
    cod = fab.articulo(id_empresa=emp, precio=9.99, stock_total=0)
    fab.al_limpiar(lambda: _borra(db, emp, cod))
    _recepcion(emp, cod, 5, 3.00)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT precio FROM articulos WHERE codigo=%s", (cod,))
        precio = float(cur.fetchone()[0])
    assert precio == 9.99                          # PVP intacto
    assert C.obtener_costes(cod)["ultimo_coste"] == 3.00
