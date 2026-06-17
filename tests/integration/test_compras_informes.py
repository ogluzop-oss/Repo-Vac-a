"""E2.6 · Informes de compras: por proveedor/periodo, costes por artículo, ranking."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_facturas WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


@pytest.fixture
def escenario(db, fab):
    from src.db import compras as C, proveedores as P
    emp = fab.empresa("INF COMPRAS")
    fab.al_limpiar(lambda: _borra(db, emp))
    p1 = P.crear_proveedor("PROVEEDOR UNO", id_empresa=emp)
    p2 = P.crear_proveedor("PROVEEDOR DOS", id_empresa=emp)
    # Pedidos (para ranking/histórico).
    C.crear_pedido(id_proveedor=p1, lineas=[{"codigo": "A", "cantidad": 1, "precio_unitario": 10}], id_empresa=emp)
    C.crear_pedido(id_proveedor=p1, lineas=[{"codigo": "A", "cantidad": 1, "precio_unitario": 10}], id_empresa=emp)
    C.crear_pedido(id_proveedor=p2, lineas=[{"codigo": "B", "cantidad": 1, "precio_unitario": 5}], id_empresa=emp)
    # Facturas (para gasto/periodo/costes por artículo).
    C.registrar_factura(id_proveedor=p1, numero_factura="F1", fecha_factura="2026-01-10",
                        lineas=[{"codigo": "A", "cantidad": 10, "precio_unitario": 2.0}], id_empresa=emp)
    C.registrar_factura(id_proveedor=p1, numero_factura="F2", fecha_factura="2026-02-05",
                        lineas=[{"codigo": "A", "cantidad": 5, "precio_unitario": 3.0}], id_empresa=emp)
    C.registrar_factura(id_proveedor=p2, numero_factura="F3", fecha_factura="2026-02-20",
                        lineas=[{"codigo": "B", "cantidad": 4, "precio_unitario": 1.0}], id_empresa=emp)
    return emp, p1, p2


def test_compras_por_proveedor(escenario):
    from src.db import compras as C
    emp, p1, p2 = escenario
    rep = {r["id_proveedor"]: r for r in C.compras_por_proveedor(id_empresa=emp)}
    assert float(rep[p1]["total"]) == 35.0 and rep[p1]["facturas"] == 2   # 20 + 15
    assert float(rep[p2]["total"]) == 4.0
    assert rep[p1]["proveedor"] == "PROVEEDOR UNO"


def test_compras_por_periodo(escenario):
    from src.db import compras as C
    emp, *_ = escenario
    per = {r["periodo"]: float(r["total"]) for r in C.compras_por_periodo(id_empresa=emp)}
    assert per["2026-01"] == 20.0 and per["2026-02"] == 19.0       # 15 + 4
    # Filtro por rango.
    solo_ene = C.compras_por_periodo(desde="2026-01-01", hasta="2026-01-31", id_empresa=emp)
    assert len(solo_ene) == 1 and solo_ene[0]["periodo"] == "2026-01"


def test_costes_por_articulo(escenario):
    from src.db import compras as C
    emp, *_ = escenario
    cpa = {r["codigo_articulo"]: r for r in C.costes_por_articulo(id_empresa=emp)}
    assert cpa["A"]["unidades"] == 15 and float(cpa["A"]["gasto"]) == 35.0
    assert cpa["A"]["precio_medio"] == round(35.0 / 15, 2)


def test_ranking_e_historico(escenario):
    from src.db import compras as C
    emp, p1, p2 = escenario
    ranking = C.proveedores_mas_utilizados(id_empresa=emp)
    assert ranking[0]["id_proveedor"] == p1 and ranking[0]["pedidos"] == 2
    assert len(C.historico_pedidos(id_empresa=emp)) == 3
    assert len(C.historico_pedidos(id_empresa=emp, id_proveedor=p2)) == 1
