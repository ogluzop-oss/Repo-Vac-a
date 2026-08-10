"""
Tests PCD · Etapa B · Fase B6: Pasarelas de pago.

Verifica que el pago REUTILIZA la pasarela existente (provider-agnostic, degradable a 'simulado'),
lleva la Transacción CONFIRMADA → PAGADA sin mover stock, es idempotente, y procesa webhooks firmados
(HMAC) con deduplicación. Multiempresa.
"""

import hashlib
import hmac
import inspect

import pytest

EMP = "T-PAY-A"
COD = "PAY1"


@pytest.fixture()
def pedido(db):
    """Crea un checkout CONFIRMADO (tx + reserva) sobre el que cobrar."""
    def _clean(cur):
        for t in ("cd_pagos", "transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial", "cd_reservas", "cd_conexiones"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_central) "
                    "VALUES (%s,%s,'Pago Test',40.0,10)", (COD, EMP))
        conn.commit()
    from src.services.comercio_digital import checkout
    r = checkout.confirmar(id_empresa=EMP, origen="web",
                           lineas=[{"codigo": COD, "cantidad": 2, "precio_unitario": 40.0}])
    yield r["id_tx"]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()


def test_iniciar_pago_simulado(pedido):
    from src.services.comercio_digital import pagos
    r = pagos.iniciar(pedido, proveedor="simulado", id_empresa=EMP)
    assert r["ok"] and r["referencia"].startswith("SIM-") and r["importe"] == 80.0
    assert pagos.estado(pedido, id_empresa=EMP) == "iniciado"


def test_confirmar_lleva_a_pagada_sin_mover_stock(pedido, db):
    from src.services.comercio_digital import pagos, transacciones
    pagos.iniciar(pedido, proveedor="simulado", id_empresa=EMP)
    r = pagos.confirmar(pedido, id_empresa=EMP)
    assert r["ok"] and r["estado"] == "PAGADA"
    assert transacciones.obtener(pedido, EMP)["estado"] == "PAGADA"
    assert pagos.estado(pedido, id_empresa=EMP) == "pagado"
    # El stock físico NO se movió con el pago (política única en el cumplimiento).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_central FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        s = cur.fetchone()
    assert int(list(s.values())[0] if isinstance(s, dict) else s[0]) == 10


def test_cobrar_express_simulado_lleva_a_pagada(pedido, db):
    """Cobro en 1 clic: en 'simulado' auto-confirma → PAGADA (marcado como simulado, no cobro real)."""
    from src.services.comercio_digital import pagos, transacciones
    r = pagos.cobrar_express(pedido, proveedor="simulado", id_empresa=EMP)
    assert r["ok"] and r["simulado"] is True and r["estado"] == "PAGADA"
    assert transacciones.obtener(pedido, EMP)["estado"] == "PAGADA"
    assert pagos.estado(pedido, id_empresa=EMP) == "pagado"
    # Idempotente: repetir no rompe (el pago ya está pagado).
    r2 = pagos.cobrar_express(pedido, proveedor="simulado", id_empresa=EMP)
    assert r2["ok"] is True


def test_confirmar_idempotente(pedido):
    from src.services.comercio_digital import pagos
    pagos.iniciar(pedido, proveedor="simulado", id_empresa=EMP)
    assert pagos.confirmar(pedido, id_empresa=EMP)["ok"]
    r2 = pagos.confirmar(pedido, id_empresa=EMP)
    assert r2["ok"] and r2.get("idempotente") is True     # segundo confirm no repite


def test_webhook_firmado_y_dedup(pedido):
    from src.services.comercio_digital import conexiones, pagos, transacciones
    conexiones.registrar("simulado", id_empresa=EMP, tipo_auth="hmac",
                         credenciales={"webhook_secret": "WHSEC"})
    ini = pagos.iniciar(pedido, proveedor="simulado", id_empresa=EMP)
    ref = ini["referencia"]
    cuerpo = f'{{"id":"evt1","referencia":"{ref}","estado":"pagado"}}'
    firma = hmac.new(b"WHSEC", cuerpo.encode(), hashlib.sha256).hexdigest()
    payload = {"id": "evt1", "referencia": ref, "estado": "pagado"}
    r = pagos.webhook("simulado", payload, firma=firma, cuerpo_raw=cuerpo, event_id="evt1",
                      id_empresa=EMP)
    assert r["ok"] and transacciones.obtener(pedido, EMP)["estado"] == "PAGADA"
    # Reenvío del mismo webhook → duplicado.
    r2 = pagos.webhook("simulado", payload, firma=firma, cuerpo_raw=cuerpo, event_id="evt1",
                       id_empresa=EMP)
    assert r2.get("duplicado") is True
    # Firma inválida → rechazo.
    r3 = pagos.webhook("simulado", {"id": "evt2", "referencia": ref, "estado": "pagado"},
                       firma="bad", cuerpo_raw="x", event_id="evt2", id_empresa=EMP)
    assert r3["ok"] is False and r3["motivo"] == "firma inválida"


def test_provider_agnostic_no_pasarela_nueva():
    from src.services.comercio_digital import pagos
    src = inspect.getsource(pagos)
    # Reutiliza la pasarela vía capacidad; no implementa una pasarela concreta ni guarda credenciales.
    assert "capabilities" in src and "pasarela_para" in src
    for prohibido in ("class PasarelaStripe", "import stripe", "api_key =", "secret_key ="):
        assert prohibido not in src
    d = pagos.descriptor()
    assert d["crea_pasarela_nueva"] is False and d["provider_agnostic"] is True
    assert d["mueve_stock"] is False and d["credenciales_en_codigo"] is False


def test_aislamiento_multiempresa(pedido):
    from src.services.comercio_digital import pagos
    pagos.iniciar(pedido, proveedor="simulado", id_empresa=EMP)
    assert pagos.estado(pedido, id_empresa=EMP) == "iniciado"
    assert pagos.estado(pedido, id_empresa="T-PAY-OTRA") is None
