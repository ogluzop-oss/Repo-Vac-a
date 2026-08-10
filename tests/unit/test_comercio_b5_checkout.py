"""
Tests PCD · Etapa B · Fase B5: Checkout completo (convergencia).

Verifica que el checkout ORQUESTA todo el ecosistema: cotización comercial → Availability →
Fulfillment → Reservation Ledger → Transacción Comercial; que la reserva reduce el ATP y queda ligada
a la Transacción; que sin stock no confirma; que cancelar libera; que registra la decisión (Audit
Replay) y NO mueve stock. Multiempresa.
"""

import inspect

import pytest

EMP = "T-CHK-A"
COD = "CHK1"


@pytest.fixture()
def art(db):
    def _clean(cur):
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial", "cd_reservas", "cd_precios_lista", "cupones",
                  "promociones"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_tienda, "
                    "Stock_central) VALUES (%s,%s,'Checkout Test',50.0,0,10)", (COD, EMP))
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()


def _atp_central(emp):
    from src.services.comercio_digital.inventario import availability as av
    d = av.disponibilidad(COD, 1, id_empresa=emp, id_tienda=None)
    return next(b["disponible"] for b in d["buckets"] if b["bucket"] == "central")


def test_preparar_vista_previa_sin_efectos(art):
    from src.services.comercio_digital import checkout
    r = checkout.preparar(id_empresa=EMP, lineas=[{"codigo": COD, "cantidad": 2,
                                                   "precio_unitario": 50.0}])
    assert r["ok"] and r["disponible"] is True and r["total"] == 100.0
    # No reservó nada (ATP intacto).
    assert _atp_central(EMP) == 10


def test_confirmar_convergencia_completa(art, db):
    from src.services.comercio_digital import checkout, transacciones
    r = checkout.confirmar(id_empresa=EMP, origen="web",
                           lineas=[{"codigo": COD, "cantidad": 3, "precio_unitario": 50.0}])
    assert r["ok"] and r["id_tx"] and r["total"] == 150.0 and r["reservas"]
    # Transacción CONFIRMADA con origen del canal.
    t = transacciones.obtener(r["id_tx"], EMP)
    assert t["estado"] == "CONFIRMADA" and t["origen"] == "web"
    # La reserva (ligada a la Transacción) redujo el ATP: 10 - 3 = 7.
    assert _atp_central(EMP) == 7
    # Decisión registrada (Audit Replay).
    rec = transacciones.reconstruir(r["id_tx"], EMP)
    assert any(d["motor"] == "checkout" for d in rec["decisiones"])
    # El stock físico NO se movió (política única).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_central FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        r2 = cur.fetchone()
        assert int(list(r2.values())[0] if isinstance(r2, dict) else r2[0]) == 10


def test_confirmar_aplica_promocion(art):
    from src.db import promociones as promo
    from src.services.comercio_digital import checkout
    promo.crear_promocion("10% CHK", tipo="descuento_pct", valor=10, ambito="articulo",
                          reglas=[{"clave": "codigo", "valor": COD}], id_empresa=EMP)
    r = checkout.confirmar(id_empresa=EMP, lineas=[{"codigo": COD, "cantidad": 2,
                                                    "precio_unitario": 50.0}])
    assert r["ok"] and r["total"] == 90.0        # 100 - 10% = 90 (cotización aplicada)


def test_sin_stock_no_confirma(art):
    from src.services.comercio_digital import checkout
    r = checkout.confirmar(id_empresa=EMP, lineas=[{"codigo": COD, "cantidad": 999,
                                                    "precio_unitario": 50.0}])
    assert r["ok"] is False and r["motivo"] == "sin disponibilidad"
    assert _atp_central(EMP) == 10               # no reservó nada


def test_cancelar_libera_reservas(art):
    from src.services.comercio_digital import checkout
    r = checkout.confirmar(id_empresa=EMP, lineas=[{"codigo": COD, "cantidad": 4,
                                                    "precio_unitario": 50.0}])
    assert _atp_central(EMP) == 6
    c = checkout.cancelar(r["id_tx"], id_empresa=EMP)
    assert c["ok"] and c["reservas_liberadas"] >= 1 and c["estado"] == "CANCELADA"
    assert _atp_central(EMP) == 10               # ATP restaurado


def test_no_motor_ni_stock():
    from src.services.comercio_digital import checkout
    src = inspect.getsource(checkout)
    # Orquesta; no reimplementa inventario/pagos ni mueve stock.
    for prohibido in ("INSERT INTO articulos", "UPDATE articulos", "kardex", "CREATE TABLE"):
        assert prohibido not in src
    d = checkout.descriptor()
    assert d["mueve_stock"] is False and d["cobra"] is False and d["crea_motor_nuevo"] is False
    assert set(d["orquesta"]) >= {"comercial", "reservas", "transacciones"}
