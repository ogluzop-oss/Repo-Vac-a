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


def test_pagado_solo_reserva_no_descuenta_stock_fisico(db, fab):
    """Capa de seguridad adicional (CD-005 Fase 5, petición explícita — ver docstring de
    `crear_pedido_online`): el stock físico NO se descuenta al pagar, solo se RESERVA (Reservation
    Ledger) — así ninguna tienda/canal vende en silencio algo ya comprometido. El descuento físico
    real ocurre más tarde, al pasar a ENVIADO (`test_envio_descuenta_stock_fisico_idempotente`)."""
    from src.services.comercio_digital.inventario import reservas as RSV
    from src.services.tpv import online_orders_service as OS
    cod = fab.articulo(stock_total=5)
    pid = OS.crear_pedido_online({"nombre": "Cliente"},
                                 [{"codigo": cod, "cantidad": 2, "precio": 1.0, "subtotal": 2.0}],
                                 estado="PAGADO")
    _limpia_pedido(db, fab, pid)
    assert _stock(db, cod) == 5                        # sin cambios: solo reservado, no descontado
    assert RSV.reservado(cod) == 2                      # reserva activa por la cantidad del pedido
    assert OS.obtener_pedido(pid)["estado"] == "PAGADO"


def test_envio_descuenta_stock_fisico_idempotente(db, fab):
    """El descuento físico real ocurre al ENVIAR (`registrar_envio`), es idempotente (flag
    `stock_descontado`) y libera la reserva — reflejo del comportamiento real documentado en
    `_descontar_stock_pedido`/`registrar_envio`."""
    from src.services.comercio_digital.inventario import reservas as RSV
    from src.services.tpv import online_orders_service as OS
    cod = fab.articulo(stock_total=10)
    pid = OS.crear_pedido_online({"nombre": "C"},
                                 [{"codigo": cod, "cantidad": 3, "precio": 1.0, "subtotal": 3.0}],
                                 estado="PAGADO")
    _limpia_pedido(db, fab, pid)
    assert _stock(db, cod) == 10                        # aún no enviado: sin descuento físico

    OS.registrar_envio(pid)
    assert _stock(db, cod) == 7                         # 10 - 3, descontado al enviar
    assert RSV.reservado(cod) == 0                       # la reserva se libera al descontar de verdad

    OS.registrar_envio(pid)                             # reenviar/reintentar no debe re-descontar
    assert _stock(db, cod) == 7


def test_cancelado_sin_envio_no_toca_stock_y_libera_reserva(db, fab):
    """Cancelar un pedido que NUNCA llegó a enviarse no repone stock físico porque nunca se llegó
    a descontar (`_reponer_stock_pedido` es no-op si `stock_descontado` no está activo) — solo
    libera la reserva soft que lo mantenía apartado."""
    from src.services.comercio_digital.inventario import reservas as RSV
    from src.services.tpv import online_orders_service as OS
    cod = fab.articulo(stock_total=8)
    pid = OS.crear_pedido_online({"nombre": "C"},
                                 [{"codigo": cod, "cantidad": 5, "precio": 1.0, "subtotal": 5.0}],
                                 estado="PAGADO")
    _limpia_pedido(db, fab, pid)
    assert _stock(db, cod) == 8 and RSV.reservado(cod) == 5
    OS.cambiar_estado(pid, "CANCELADO")
    assert _stock(db, cod) == 8                          # nunca se descontó: nada que reponer
    assert RSV.reservado(cod) == 0                        # la reserva queda liberada


def test_listar_pedidos_aislado_por_empresa(db, fab):
    from src.services.tpv import online_orders_service as OS
    otra = fab.empresa("OTRA SL")
    fab.pedido_online(id_empresa=otra, total=99.0)     # pedido de otra empresa
    # La empresa activa (por defecto) no debe ver el pedido de 'otra'.
    refs = {p.get("id_empresa") for p in OS.listar_pedidos_online()}
    assert otra not in refs
