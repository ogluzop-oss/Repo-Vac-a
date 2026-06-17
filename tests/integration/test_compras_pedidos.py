"""E2.2 · Pedidos de compra: creación, líneas, estados, histórico."""

import pytest

pytestmark = pytest.mark.db


def _borra(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))   # cascada líneas
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _pedido(emp, fab):
    from src.db import compras as C, proveedores as P
    prov = P.crear_proveedor("PROV PEDIDOS", id_empresa=emp)
    lineas = [{"codigo": "ART001", "descripcion": "Leche", "cantidad": 10, "precio_unitario": 0.80},
              {"codigo": "ART002", "descripcion": "Pan", "cantidad": 5, "precio_unitario": 1.20}]
    pid = C.crear_pedido(id_proveedor=prov, lineas=lineas, observaciones="urgente", id_empresa=emp)
    return prov, pid


def test_crear_pedido_calcula_total(db, fab):
    from src.db import compras as C
    emp = fab.empresa("CP CREAR")
    fab.al_limpiar(lambda: _borra(db, emp))
    _, pid = _pedido(emp, fab)
    ped = C.obtener_pedido(pid, emp)
    assert ped["estado"] == "BORRADOR" and ped["numero"] == f"PC{pid:06d}"
    assert len(ped["lineas"]) == 2
    assert float(ped["total"]) == 14.0          # 10*0.80 + 5*1.20
    assert ped["lineas"][0]["subtotal"] and ped["lineas"][0]["cantidad_recibida"] == 0


def test_modificar_solo_en_borrador(db, fab):
    from src.db import compras as C
    emp = fab.empresa("CP MOD")
    fab.al_limpiar(lambda: _borra(db, emp))
    _, pid = _pedido(emp, fab)
    assert C.modificar_lineas(pid, [{"codigo": "ART001", "cantidad": 3, "precio_unitario": 1.0}], emp)
    assert float(C.obtener_pedido(pid, emp)["total"]) == 3.0
    # Tras enviar, ya no se puede modificar.
    assert C.enviar_pedido(pid, emp)
    assert C.modificar_lineas(pid, [], emp) is False


def test_transiciones_estado(db, fab):
    from src.db import compras as C
    emp = fab.empresa("CP EST")
    fab.al_limpiar(lambda: _borra(db, emp))
    _, pid = _pedido(emp, fab)
    # BORRADOR -> RECIBIDO no permitido (debe pasar por ENVIADO).
    assert C.cambiar_estado(pid, "RECIBIDO", emp) is False
    assert C.enviar_pedido(pid, emp) and C.obtener_pedido(pid, emp)["estado"] == "ENVIADO"
    assert C.cambiar_estado(pid, "PARCIAL", emp)
    assert C.cambiar_estado(pid, "RECIBIDO", emp)
    # RECIBIDO es terminal.
    assert C.cancelar_pedido(pid, emp) is False


def test_historico_y_aislamiento(db, fab):
    from src.db import compras as C
    a = fab.empresa("CP A"); b = fab.empresa("CP B")
    fab.al_limpiar(lambda: (_borra(db, a), _borra(db, b)))
    _, pid = _pedido(a, fab)
    assert [p["id_pedido"] for p in C.listar_pedidos(a)] == [pid]
    assert C.listar_pedidos(b) == []                # B no ve pedidos de A
    assert C.obtener_pedido(pid, b) is None
