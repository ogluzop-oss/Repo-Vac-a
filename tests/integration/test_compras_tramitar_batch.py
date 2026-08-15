"""Bolsa de proveedores · cola + tramitar en lote (Fase 1 · paso 3).

Los pedidos BORRADOR son la cola; `enviar_todos_borradores` los pasa TODOS a ENVIADO de una vez,
tolerando fallos individuales (no colapsa con muchos pedidos de distintos proveedores).
"""

import pytest

from src.db import compras as C
from src.db import proveedores as PROV

pytestmark = pytest.mark.db


def _limpia(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                    "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def _pedido(emp, prov, cod):
    return C.crear_pedido(id_proveedor=prov, id_empresa=emp,
                          lineas=[{"codigo": cod, "cantidad": 2, "precio_unitario": 1.0}])


def test_tramitar_todos_borradores(db, fab):
    emp = fab.empresa("EMP batch")
    fab.al_limpiar(lambda: _limpia(db, emp))
    pa = PROV.crear_proveedor("Prov A", id_empresa=emp)
    pb = PROV.crear_proveedor("Prov B", id_empresa=emp)

    p1 = _pedido(emp, pa, "X1")
    p2 = _pedido(emp, pb, "X2")
    p3 = _pedido(emp, pa, "X3")
    assert all([p1, p2, p3])
    assert len(C.listar_pedidos(id_empresa=emp, estado="BORRADOR")) == 3   # la cola

    res = C.enviar_todos_borradores(id_empresa=emp)
    assert res["total"] == 3 and res["enviados"] == 3 and res["fallidos"] == 0
    assert set(res["ids_enviados"]) == {p1, p2, p3}
    # ya no quedan borradores; los 3 están ENVIADO (de distintos proveedores, en un solo lote)
    assert C.listar_pedidos(id_empresa=emp, estado="BORRADOR") == []
    assert len(C.listar_pedidos(id_empresa=emp, estado="ENVIADO")) == 3


def test_tramitar_subconjunto_por_ids(db, fab):
    emp = fab.empresa("EMP batch 2")
    fab.al_limpiar(lambda: _limpia(db, emp))
    p = PROV.crear_proveedor("Prov C", id_empresa=emp)
    a = _pedido(emp, p, "Y1")
    b = _pedido(emp, p, "Y2")

    res = C.enviar_todos_borradores(id_empresa=emp, ids=[a])   # solo uno
    assert res["enviados"] == 1 and res["ids_enviados"] == [a]
    estados = {x["id_pedido"]: x["estado"] for x in C.listar_pedidos(id_empresa=emp)}
    assert estados[a] == "ENVIADO" and estados[b] == "BORRADOR"
