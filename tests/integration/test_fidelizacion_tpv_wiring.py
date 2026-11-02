"""
Fidelización Omnicanal (Generador de Apps Móviles PWA, Fase 3) — el motor de puntos (`db.
fidelizacion`, ya existente) ahora se invoca de verdad desde el ÚNICO punto de registro de venta
(`conexion.registrar_venta_con_items`) y desde la devolución (`tpv.refund_service.
procesar_devolucion`), en vez de quedar sin usar salvo en tests. BD real (`*_test`)."""

import pytest

from src.db import clientes as cli_db
from src.db import conexion
from src.db import fidelizacion as fid

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.empresa("FIDELIZACION TPV TEST")


def _limpia_venta(db, vid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM venta_items WHERE venta_id=%s", (vid,))
        cur.execute("DELETE FROM ventas WHERE id=%s", (vid,))
        conn.commit()


def test_venta_sin_cliente_no_acumula_puntos(db, fab, emp):
    cod = fab.articulo(id_empresa=emp, precio=10.0, stock_total=5)
    vid = conexion.registrar_venta_con_items(
        [{"codigo_articulo": cod, "cantidad": 1, "precio_unitario": 10.0}], id_empresa=emp)
    fab.al_limpiar(lambda: _limpia_venta(db, vid))
    assert vid is not None
    # Nunca lanza ni interfiere aunque no haya cliente vinculado.


def test_venta_con_cliente_acumula_puntos_reales(db, fab, emp):
    cod = fab.articulo(id_empresa=emp, precio=10.0, stock_total=5)
    cid = cli_db.crear_cliente("Cliente Fidelizado", id_empresa=emp)
    fab.al_limpiar(lambda: _borrar_cliente(db, cid))

    assert fid.saldo_puntos(cid, id_empresa=emp) == 0
    vid = conexion.registrar_venta_con_items(
        [{"codigo_articulo": cod, "cantidad": 2, "precio_unitario": 10.0}],
        cliente={"id": cid}, id_empresa=emp)
    fab.al_limpiar(lambda: _limpia_venta(db, vid))
    assert vid is not None
    # 20€ de venta -> 20 puntos (PUNTOS_POR_EURO = 1), acumulados de VERDAD, no solo "disponibles".
    assert fid.saldo_puntos(cid, id_empresa=emp) == 20
    movs = fid.movimientos(cid, id_empresa=emp)
    assert any(m["tipo"] == "acumular" and m["puntos"] == 20 and str(m["id_venta"]) == str(vid)
              for m in movs)


def test_devolucion_revierte_puntos_de_la_venta_original(db, fab, emp):
    from src.services.tpv.refund_service import procesar_devolucion
    cod = fab.articulo(id_empresa=emp, precio=10.0, stock_total=5)
    cid = cli_db.crear_cliente("Cliente Con Devolucion", id_empresa=emp)
    fab.al_limpiar(lambda: _borrar_cliente(db, cid))

    vid = conexion.registrar_venta_con_items(
        [{"codigo_articulo": cod, "cantidad": 3, "precio_unitario": 10.0}],
        cliente={"id": cid}, id_empresa=emp)
    fab.al_limpiar(lambda: _limpia_venta(db, vid))
    assert fid.saldo_puntos(cid, id_empresa=emp) == 30

    ok, msg, dev_id = procesar_devolucion(
        vid, [{"codigo_articulo": cod, "nombre": "x", "cantidad": 1,
              "precio_unitario": 10.0, "subtotal": 10.0}],
        forma_reembolso="efectivo", forma_pago_original="efectivo",
        empleado="TEST", numero_caja=1, motivo="prueba")
    assert ok, msg
    fab.al_limpiar(lambda: _limpia_devolucion(db, dev_id))

    # Se revierten los puntos proporcionales al importe devuelto (10€ -> 10 puntos), no el total.
    assert fid.saldo_puntos(cid, id_empresa=emp) == 20


def _borrar_cliente(db, cid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fidelizacion_movimientos WHERE id_cliente=%s", (cid,))
        cur.execute("DELETE FROM clientes WHERE id=%s", (cid,))
        conn.commit()


def _limpia_devolucion(db, dev_id):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM devolucion_items WHERE devolucion_id=%s", (dev_id,))
        cur.execute("DELETE FROM devoluciones WHERE id=%s", (dev_id,))
        conn.commit()
