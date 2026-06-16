"""Integración · transacciones reales y locking efectivo (A2.2)."""

import threading

import pytest

pytestmark = pytest.mark.db


def _stock(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(Stock_total,0)+COALESCE(Stock_tienda,0) FROM articulos WHERE codigo=%s",
                    (cod,))
        return int(cur.fetchone()[0])


def test_transaccion_commit(db, fab):
    cod = fab.articulo(stock_total=10)
    with db.transaccion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE articulos SET Stock_total=3 WHERE codigo=%s", (cod,))
    assert _stock(db, cod) == 3


def test_transaccion_rollback(db, fab):
    cod = fab.articulo(stock_total=10)
    with pytest.raises(RuntimeError):
        with db.transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE articulos SET Stock_total=0 WHERE codigo=%s", (cod,))
            raise RuntimeError("boom")
    # El rollback deja el stock intacto.
    assert _stock(db, cod) == 10


def test_descontar_stock_sin_sobreventa_concurrente(db, fab):
    """10 hilos compran la última unidad de un stock de 5: exactamente 5 con éxito,
    y NUNCA queda stock negativo (FOR UPDATE efectivo dentro de transacción)."""
    cod = fab.articulo(stock_total=5, stock_tienda=0)
    exitos = []

    def comprar():
        ok, _t, _ti = db.descontar_stock(cod, 1)
        exitos.append(ok)

    hilos = [threading.Thread(target=comprar) for _ in range(10)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sum(1 for e in exitos if e) == 5
    assert _stock(db, cod) == 0          # nunca negativo


def test_registrar_venta_atomica_y_for_update(db, fab):
    from src.utils import registro_venta as RV
    cod = fab.articulo(stock_tienda=2)
    fab.al_limpiar(lambda: _borra_ventas(db, cod))
    assert RV.registrar_venta(cod, 1) is True
    assert _stock(db, cod) == 1
    # Stock insuficiente → no registra ni descuenta.
    assert RV.registrar_venta(cod, 5) is False
    assert _stock(db, cod) == 1


def test_crear_pedido_online_atomico(db, fab):
    from src.services.tpv import online_orders_service as OS
    cod = fab.articulo(stock_total=5)
    pid = OS.crear_pedido_online({"nombre": "Tx"},
                                 [{"codigo": cod, "cantidad": 2, "precio": 1.0, "subtotal": 2.0}],
                                 estado="PENDIENTE")
    fab.al_limpiar(lambda: _borra_pedido(db, pid))
    ped = OS.obtener_pedido(pid)
    assert ped and len(ped["items"]) == 1     # pedido e ítems persistidos juntos


def _borra_ventas(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ventas WHERE codigo=%s", (cod,))
        conn.commit()


def _borra_pedido(db, pid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM pedidos_online_items WHERE id_pedido=%s", (pid,))
        cur.execute("DELETE FROM pedidos_online WHERE id_pedido=%s", (pid,))
        conn.commit()
