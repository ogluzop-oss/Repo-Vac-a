"""
Distribución mayorista B2B (R8·it3, FUNCIÓN BASE): orquesta la cadena EXISTENTE
pedido → picking → expedición → salida de stock OFICIAL. Cero lógica paralela: el stock sale por
`convertir_a_venta` (kárdex SALIDA_VENTA), el picking por `almacen_pro`, la expedición por `logistica_pro`.
Verticales: la función es visible solo en las versiones de comercio general (SUPERMARKET/RETAIL).
"""

import pytest

pytestmark = pytest.mark.db

from src.services import expediciones as D


@pytest.fixture
def emp(fab):
    return fab.empresa("DISTRIB R8")


def _articulo(db, emp, cod, stock, precio=10.0):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,precio,Stock_tienda,Stock_total) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE precio=%s,Stock_tienda=%s,Stock_total=%s",
                    (cod, emp, cod, precio, stock, stock, precio, stock, stock))
        c.commit()


def _stock(db, emp, cod):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT Stock_tienda FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        r = cur.fetchone()
        return int((r[0] if r else 0) or 0)


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    def _borra():
        with db.obtener_conexion() as c, c.cursor() as cur:
            for t in ("ventas_pedidos_cliente_lineas", "ventas_pedidos_cliente",
                      "almacen_picking_lineas", "almacen_picking", "logistica_expediciones", "clientes"):
                try:
                    cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
                except Exception:
                    pass
            cur.execute("DELETE FROM articulos WHERE codigo='DST-A' AND id_empresa=%s", (emp,))
            cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo='DST-A'")
            cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
            c.commit()
    yield
    _borra()


def _cliente(emp):
    from src.db.clientes import crear_cliente
    return crear_cliente("Mayorista SL", nif="B00000000", id_empresa=emp)


def test_flujo_pedido_picking_expedicion(db, emp):
    from src.db.empresa import contexto_tenant

    _articulo(db, emp, "DST-A", 20, precio=10.0)
    cli = _cliente(emp)
    pid = D.crear_pedido(cli, [{"codigo": "DST-A", "cantidad": 5}], id_empresa=emp)
    assert pid, "pedido creado"

    # Preparar → crea un picking ligado al pedido (reutiliza almacen_pro).
    pick = D.preparar(pid, responsable="Almacén", id_empresa=emp)
    assert pick, "picking creado"
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT id_documento FROM almacen_picking WHERE id=%s AND id_empresa=%s", (pick, emp))
        assert int(cur.fetchone()[0]) == pid            # picking ligado al pedido
    assert _stock(db, emp, "DST-A") == 20               # preparar NO mueve stock

    # Expedir → salida de stock OFICIAL (SALIDA_VENTA) + expedición registrada.
    with contexto_tenant(emp, None):
        r = D.expedir(pid, direccion="Muelle 1", id_empresa=emp)
    assert r["ok"] and r["venta_id"], r
    assert _stock(db, emp, "DST-A") == 15               # 20 - 5 por el motor oficial
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE codigo_articulo='DST-A' "
                    "AND tipo_movimiento='SALIDA_VENTA'")
        assert (cur.fetchone()[0] or 0) >= 1            # kárdex oficial
        cur.execute("SELECT COUNT(*) FROM logistica_expediciones WHERE id_empresa=%s AND origen='pedido' "
                    "AND id_documento=%s", (emp, pid))
        assert (cur.fetchone()[0] or 0) == 1            # expedición registrada


def test_expedir_no_duplica_stock(db, emp):
    from src.db.empresa import contexto_tenant
    _articulo(db, emp, "DST-A", 20)
    cli = _cliente(emp)
    pid = D.crear_pedido(cli, [{"codigo": "DST-A", "cantidad": 4}], id_empresa=emp)
    with contexto_tenant(emp, None):
        assert D.expedir(pid, id_empresa=emp)["ok"] is True
        r2 = D.expedir(pid, id_empresa=emp)             # 2ª vez: pedido ya convertido
    assert r2["ok"] is False
    assert _stock(db, emp, "DST-A") == 16               # 20 - 4 una sola vez


def test_precio_mayorista_si_existe(db, emp):
    _articulo(db, emp, "DST-A", 20, precio=10.0)
    from src.services.comercio_digital.comercial import fijar_precio
    fijar_precio("mayorista", "DST-A", 7.5, id_empresa=emp)     # tarifa mayorista
    cli = _cliente(emp)
    pid = D.crear_pedido(cli, [{"codigo": "DST-A", "cantidad": 2}], id_empresa=emp)   # sin precio → mayorista
    ped = None
    from src.db import ventas_comercial as VC
    ped = VC.obtener_pedido_cliente(pid, id_empresa=emp)
    assert float(ped["lineas"][0]["precio_unitario"]) == 7.5    # aplicó la tarifa mayorista


def test_distribucion_solo_comercio_general_con_almacen():
    from src.services import verticales as V
    # Distribución mayorista B2B: solo Supermarket, Retail y Textil.
    for e in ("SUPERMARKET", "RETAIL", "TEXTIL"):
        assert V.visible("distribucion.expedicion", vertical=e) is True
    for e in ("PHARMACY", "BAKERY"):
        assert V.visible("distribucion.expedicion", vertical=e) is False
