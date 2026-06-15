"""Integración · ciclo de vida del pedido online: stock, idempotencia, reposición."""

import os

import pytest

pytestmark = pytest.mark.db


def _stock(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(Stock_total,0)+COALESCE(Stock_tienda,0) FROM articulos WHERE codigo=%s",
                    (cod,))
        return int(cur.fetchone()[0])


def _limpia_pedido(db, fab, pid):
    def _f():
        for sql in ("DELETE FROM pedidos_online_items WHERE id_pedido=%s",
                    "DELETE FROM documentos_registro WHERE referencia=%s",
                    "DELETE FROM pedidos_online WHERE id_pedido=%s"):
            with db.obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(sql, (pid,)); conn.commit()
        for pre in ("justificante_pago", "comprobante_pedido", "envio_pedido"):
            f = os.path.join("documentos", "pedidos", f"{pre}_{pid}.pdf")
            if os.path.exists(f):
                os.remove(f)
    fab.al_limpiar(_f)


def test_pagado_descuenta_stock(db, fab):
    from src.services.tpv import online_orders_service as OS
    cod = fab.articulo(stock_total=5)
    pid = OS.crear_pedido_online({"nombre": "Cliente"},
                                 [{"codigo": cod, "cantidad": 2, "precio": 1.0, "subtotal": 2.0}],
                                 estado="PAGADO")
    _limpia_pedido(db, fab, pid)
    assert _stock(db, cod) == 3                       # 5 - 2
    assert OS.obtener_pedido(pid)["estado"] == "PAGADO"


def test_pagado_idempotente(db, fab):
    from src.services.tpv import online_orders_service as OS
    cod = fab.articulo(stock_total=10)
    pid = OS.crear_pedido_online({"nombre": "C"},
                                 [{"codigo": cod, "cantidad": 3, "precio": 1.0, "subtotal": 3.0}],
                                 estado="PAGADO")
    _limpia_pedido(db, fab, pid)
    assert _stock(db, cod) == 7
    OS.cambiar_estado(pid, "PAGADO")                  # re-confirmar no debe re-descontar
    assert _stock(db, cod) == 7


def test_cancelado_repone_stock(db, fab):
    from src.services.tpv import online_orders_service as OS
    cod = fab.articulo(stock_total=8)
    pid = OS.crear_pedido_online({"nombre": "C"},
                                 [{"codigo": cod, "cantidad": 5, "precio": 1.0, "subtotal": 5.0}],
                                 estado="PAGADO")
    _limpia_pedido(db, fab, pid)
    assert _stock(db, cod) == 3
    OS.cambiar_estado(pid, "CANCELADO")
    assert _stock(db, cod) == 8                        # repuesto


def test_listar_pedidos_aislado_por_empresa(db, fab):
    from src.services.tpv import online_orders_service as OS
    otra = fab.empresa("OTRA SL")
    fab.pedido_online(id_empresa=otra, total=99.0)     # pedido de otra empresa
    # La empresa activa (por defecto) no debe ver el pedido de 'otra'.
    refs = {p.get("id_empresa") for p in OS.listar_pedidos_online()}
    assert otra not in refs
