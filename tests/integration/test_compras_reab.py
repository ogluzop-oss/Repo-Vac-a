"""E2.7 · Integración reabastecimiento → borrador de pedido de compra."""

import pytest

pytestmark = pytest.mark.db

_CODS = ("REAB_E27_A", "REAB_E27_B")


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        for c in _CODS:
            cur.execute("DELETE FROM reab_propuestas WHERE codigo=%s", (c,))
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (c,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_propuestas_a_borrador_de_compra(db, fab):
    from src.db import compras as C, reabastecimiento as R
    emp = fab.empresa("REAB COMPRA")
    fab.al_limpiar(lambda: _borra(db, emp))
    # Artículos con coste (para precio estimado del pedido).
    fab.articulo(codigo=_CODS[0], id_empresa=emp)
    fab.articulo(codigo=_CODS[1], id_empresa=emp)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET coste_actual=1.50 WHERE codigo=%s", (_CODS[0],))
        conn.commit()
    # Propuestas de reabastecimiento (pendientes).
    id1 = R.crear_propuesta(_CODS[0], "Artículo A", 20, "ALMACÉN CENTRAL", 2, 22)
    id2 = R.crear_propuesta(_CODS[1], "Artículo B", 8, "ALMACÉN CENTRAL", 1, 9)
    assert id1 and id2

    pid = C.crear_pedido_desde_propuestas(propuesta_ids=[id1, id2], id_empresa=emp)
    assert pid
    ped = C.obtener_pedido(pid, emp)
    assert ped["estado"] == "BORRADOR" and len(ped["lineas"]) == 2
    porcod = {l["codigo_articulo"]: l for l in ped["lineas"]}
    assert porcod[_CODS[0]]["cantidad"] == 20 and float(porcod[_CODS[0]]["precio_unitario"]) == 1.50
    assert porcod[_CODS[1]]["cantidad"] == 8
    # Las propuestas pasan a 'pedido' (ya no pendientes).
    pendientes = {p["id"] for p in R.listar_propuestas(("pendiente",))}
    assert id1 not in pendientes and id2 not in pendientes


def test_sin_propuestas_no_crea_pedido(db, fab):
    from src.db import compras as C
    emp = fab.empresa("REAB VACIO")
    fab.al_limpiar(lambda: _borra(db, emp))
    assert C.crear_pedido_desde_propuestas(propuesta_ids=[999999], id_empresa=emp) is None
