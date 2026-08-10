"""
Tests Etapa C0 · Prioridad 3: cierre del ciclo de cumplimiento (política única compartida).

Verifica que la salida oficial de stock se extrajo a UN servicio reutilizable (`db.salida_stock`) sin
cambiar el comportamiento del TPV, y que el cumplimiento del Comercio Digital (envío) reutiliza EXACTA-
MENTE ese servicio: reserva CONSUMED → salida física real (clamp + kárdex + FEFO) sin crear una segunda
venta ni una segunda política. Idempotente. Consistente con Availability y el Reservation Ledger.
"""

import pytest

EMP = "T-P3-A"


def _kardex_salidas(db, id_doc):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE tipo_movimiento='SALIDA_VENTA' "
                    "AND id_documento=%s AND id_empresa=%s", (str(id_doc), EMP))
        r = cur.fetchone()
        return int(list(r.values())[0] if isinstance(r, dict) else r[0])


def _stock_tienda(db, cod):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(Stock_tienda,0) FROM articulos WHERE codigo=%s AND id_empresa=%s",
                    (cod, EMP))
        r = cur.fetchone()
        return int(list(r.values())[0] if isinstance(r, dict) else r[0])


@pytest.fixture()
def art(db):
    def _clean(cur):
        for t in ("cd_envios", "cd_pagos", "cd_reservas", "transaccion_decisiones",
                  "transaccion_eventos", "transaccion_lineas", "transaccion_comercial"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
        cur.execute("DELETE FROM movimientos_stock WHERE id_empresa=%s AND codigo_articulo='P3ART'",
                    (EMP,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo='P3ART' AND id_empresa=%s", (EMP,))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda, "
                    "Stock_central) VALUES ('P3ART',%s,'P3',20.0,10,0)", (EMP,))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo='P3ART' AND id_empresa=%s", (EMP,))
        conn.commit()


def test_servicio_ledger_idempotente(art, db):
    from src.db import salida_stock as ss
    ss.salida_stock_ledger("P3ART", 2, id_documento="DOC1", id_empresa=EMP, id_tienda=None)
    ss.salida_stock_ledger("P3ART", 2, id_documento="DOC1", id_empresa=EMP, id_tienda=None)
    assert _kardex_salidas(db, "DOC1") == 1        # kárdex idempotente por (codigo, tipo, id_documento)


def test_salida_oficial_decrementa_y_kardex(art, db):
    from src.db import salida_stock as ss
    r = ss.salida_stock_oficial("P3ART", 3, id_documento="DOC2", id_empresa=EMP, id_tienda=None)
    assert "faltante" in r
    assert _stock_tienda(db, "P3ART") == 7         # clamp físico (10-3)
    assert _kardex_salidas(db, "DOC2") == 1


def test_tpv_comportamiento_identico(db):
    """La venta de sala sigue: decremento físico + kárdex SALIDA_VENTA (ahora vía servicio compartido)."""
    from src.db.conexion import registrar_venta_con_items
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM articulos WHERE codigo='P3TPV' AND id_empresa=%s", (EMP,))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda) "
                    "VALUES ('P3TPV',%s,'TPV',5.0,10)", (EMP,))
        conn.commit()
    vid = registrar_venta_con_items([{"codigo_articulo": "P3TPV", "cantidad": 4, "precio_unitario": 5,
                                      "subtotal": 20}], forma_pago="efectivo", total=20.0,
                                    id_empresa=EMP, id_tienda=0)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(Stock_tienda,0) FROM articulos WHERE codigo='P3TPV' AND "
                    "id_empresa=%s", (EMP,))
        st = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM movimientos_stock WHERE tipo_movimiento='SALIDA_VENTA' AND "
                    "id_documento=%s AND id_empresa=%s", (str(vid), EMP))
        km = cur.fetchone()
    assert int(list(st.values())[0] if isinstance(st, dict) else st[0]) == 6    # 10-4 (idéntico)
    assert int(list(km.values())[0] if isinstance(km, dict) else km[0]) == 1    # kárdex SALIDA_VENTA
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM movimientos_stock WHERE id_documento=%s AND id_empresa=%s", (str(vid), EMP))
        cur.execute("DELETE FROM venta_items WHERE venta_id=%s", (vid,))
        cur.execute("DELETE FROM ventas WHERE id=%s", (vid,))
        cur.execute("DELETE FROM articulos WHERE codigo='P3TPV' AND id_empresa=%s", (EMP,))
        conn.commit()


def test_cierre_ciclo_ecommerce(art, db):
    """checkout → pago → envío: la reserva CONSUMED ejecuta la salida física REAL por el mismo servicio."""
    from src.services.comercio_digital import checkout, envios, pagos
    r = checkout.confirmar(id_empresa=EMP, origen="web",
                           lineas=[{"codigo": "P3ART", "cantidad": 3, "precio_unitario": 20.0}])
    tx = r["id_tx"]
    pagos.iniciar(tx, proveedor="simulado", id_empresa=EMP)
    pagos.confirmar(tx, id_empresa=EMP)
    assert _stock_tienda(db, "P3ART") == 10                 # aún no ha salido
    env = envios.crear_envio(tx, transportista="simulado", id_empresa=EMP)
    snd = envios.marcar_enviado(env["id_envio"], id_empresa=EMP)
    assert snd["ok"] and snd["reservas_consumidas"] == 1 and snd["salidas_stock"] == 1
    assert _stock_tienda(db, "P3ART") == 7                  # SALIDA física real (10-3)
    assert _kardex_salidas(db, tx) == 1                     # kárdex SALIDA por el pedido (id_tx)
    # No se ha creado ninguna venta (no 2ª venta, no doble contabilidad).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ventas WHERE id_empresa=%s", (EMP,))
        nv = cur.fetchone()
    assert int(list(nv.values())[0] if isinstance(nv, dict) else nv[0]) == 0
    # Idempotente: reenviar no vuelve a descontar (reserva ya consumida).
    snd2 = envios.marcar_enviado(env["id_envio"], id_empresa=EMP)
    assert snd2["reservas_consumidas"] == 0 and _stock_tienda(db, "P3ART") == 7


def test_un_solo_servicio_compartido():
    import inspect

    from src.db import salida_stock
    from src.db import conexion
    from src.services.comercio_digital import envios
    # Ambos flujos importan el mismo servicio; ninguno reimplementa la salida.
    assert "salida_stock" in inspect.getsource(conexion.registrar_venta_con_items)
    assert "salida_stock" in inspect.getsource(envios.marcar_enviado)
    assert hasattr(salida_stock, "salida_stock_oficial") and hasattr(salida_stock, "salida_stock_ledger")
