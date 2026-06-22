"""
Tesorería · FASE 5 — Posición de tesorería (disponible/comprometido/por_cobrar/previsto/futuro).
"""

import datetime as dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T, vencimientos as V
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.tesoreria import posicion as P

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"
IBAN2 = "DE89370400440532013000"


@pytest.fixture
def escenario(db):
    c1 = T.crear_cuenta("C1", IBAN, saldo_inicial=1000, id_empresa=E)
    c2 = T.crear_cuenta("C2", IBAN2, saldo_inicial=500, id_empresa=E)
    T.registrar_movimiento("COBRO", 200, id_cuenta=c1, id_empresa=E)     # disp c1 = 1200
    hoy = dt.date.today()
    v_cobro = V.crear_vencimiento("COBRO", 300, (hoy + dt.timedelta(days=10)).strftime("%Y-%m-%d"),
                                  origen="manual", id_documento="PC" + uuid.uuid4().hex[:6], id_empresa=E)
    v_pago = V.crear_vencimiento("PAGO", 400, (hoy + dt.timedelta(days=200)).strftime("%Y-%m-%d"),
                                 origen="manual", id_documento="PP" + uuid.uuid4().hex[:6], id_empresa=E)
    yield {"c1": c1, "c2": c2, "v_cobro": v_cobro, "v_pago": v_pago}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta IN (%s,%s)", (c1, c2))
        cur.execute("DELETE FROM cuentas_bancarias WHERE id IN (%s,%s)", (c1, c2))
        cur.execute("DELETE FROM vencimientos WHERE id IN (%s,%s)", (v_cobro, v_pago))
        conn.commit()


def test_posicion_consolidada(escenario):
    pos = P.posicion(E)
    # disponible = 1200 (c1) + 500 (c2) = 1700  (puede haber otras cuentas de otros tests? no: aislado por fixture limpio)
    assert pos["disponible"] >= 1700
    assert pos["por_cobrar"] >= 300
    assert pos["comprometido"] >= 400
    # previsto = disponible + por_cobrar - comprometido
    assert pos["previsto"] == round(pos["disponible"] + pos["por_cobrar"] - pos["comprometido"], 2)
    assert len(pos["por_cuenta"]) >= 2


def test_futuro_con_horizonte(escenario):
    pos = P.posicion(E, horizonte_dias=30)
    # a 30 días entra el cobro (día 10) pero NO el pago (día 200)
    assert pos["por_cobrar_horizonte"] >= 300
    assert pos["comprometido_horizonte"] == 0.0 or pos["comprometido_horizonte"] < 400
    assert pos["futuro"] == round(pos["disponible"] + pos["por_cobrar_horizonte"] - pos["comprometido_horizonte"], 2)
