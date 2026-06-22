"""
Tesorería · FASE 2 — Movimientos (libro financiero, saldo corrido, hash, idempotencia M1).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T
from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"


@pytest.fixture
def cuenta(db):
    cid = T.crear_cuenta("Caja Op", IBAN, saldo_inicial=100, id_empresa=E)
    yield cid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
        cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        conn.commit()


def test_saldo_corrido_y_signo(cuenta):
    T.registrar_movimiento("COBRO", 50, id_cuenta=cuenta, id_empresa=E)     # 100→150
    T.registrar_movimiento("PAGO", -30, id_cuenta=cuenta, id_empresa=E)     # 150→120
    movs = T.listar_movimientos(id_cuenta=cuenta, id_empresa=E)
    assert len(movs) == 2
    assert float(movs[0]["saldo_resultante"]) == 120.0     # más reciente primero
    assert T.saldo_cuenta(cuenta, E) == 120.0


def test_tipo_invalido_rechaza(cuenta):
    assert T.registrar_movimiento("LOQUESEA", 10, id_cuenta=cuenta, id_empresa=E) is None


def test_idempotencia_m1(cuenta):
    doc = "FRA-" + uuid.uuid4().hex[:8]
    a = T.registrar_movimiento("COBRO", 20, id_cuenta=cuenta, origen="venta",
                               id_documento=doc, idempotente=True, id_empresa=E)
    b = T.registrar_movimiento("COBRO", 20, id_cuenta=cuenta, origen="venta",
                               id_documento=doc, idempotente=True, id_empresa=E)
    assert a == b                                           # no duplica
    assert len(T.listar_movimientos(id_cuenta=cuenta, id_empresa=E)) == 1


def test_hash_encadenado(cuenta):
    T.registrar_movimiento("COBRO", 10, id_cuenta=cuenta, id_empresa=E)
    T.registrar_movimiento("COBRO", 10, id_cuenta=cuenta, id_empresa=E)
    movs = T.listar_movimientos(id_cuenta=cuenta, id_empresa=E)
    assert all(m["hash"] and len(m["hash"]) == 64 for m in movs)
    assert movs[0]["hash"] != movs[1]["hash"]


def test_transferencia_entre_cuentas(db):
    c1 = T.crear_cuenta("Origen", IBAN, saldo_inicial=200, id_empresa=E)
    c2 = T.crear_cuenta("Destino", "DE89370400440532013000", saldo_inicial=0, id_empresa=E)
    try:
        m1, m2, ref = T.transferencia(c1, c2, 75, id_empresa=E)
        assert m1 and m2 and ref
        assert T.saldo_cuenta(c1, E) == 125.0
        assert T.saldo_cuenta(c2, E) == 75.0
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta IN (%s,%s)", (c1, c2))
            cur.execute("DELETE FROM cuentas_bancarias WHERE id IN (%s,%s)", (c1, c2))
            conn.commit()
