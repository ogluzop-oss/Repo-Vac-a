"""
Tesorería · FASE 6 — Cash flow (real/previsto, granularidades, acumulado).
"""

import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T, vencimientos as V
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.tesoreria import cashflow as CF

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"


@pytest.fixture
def datos(db):
    cid = T.crear_cuenta("CF", IBAN, saldo_inicial=0, id_empresa=E)
    T.registrar_movimiento("COBRO", 100, id_cuenta=cid, fecha="2026-01-15", id_empresa=E)
    T.registrar_movimiento("PAGO", -40, id_cuenta=cid, fecha="2026-01-20", id_empresa=E)
    T.registrar_movimiento("COBRO", 200, id_cuenta=cid, fecha="2026-02-10", id_empresa=E)
    v1 = V.crear_vencimiento("COBRO", 500, "2026-03-01", origen="manual", id_documento="CF" + uuid.uuid4().hex[:6], id_empresa=E)
    v2 = V.crear_vencimiento("PAGO", 150, "2026-03-15", origen="manual", id_documento="CF" + uuid.uuid4().hex[:6], id_empresa=E)
    yield {"cid": cid, "v1": v1, "v2": v2}
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
        cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        cur.execute("DELETE FROM vencimientos WHERE id IN (%s,%s)", (v1, v2))
        conn.commit()


def test_flujo_real_mensual_acumulado(datos):
    f = CF.flujo_real(E, desde="2026-01-01", hasta="2026-02-28", granularidad="mensual")
    ene = [x for x in f if x["periodo"] == "2026-01"][0]
    feb = [x for x in f if x["periodo"] == "2026-02"][0]
    assert ene["entradas"] == 100.0 and ene["salidas"] == 40.0 and ene["neto"] == 60.0
    assert feb["entradas"] == 200.0 and feb["neto"] == 200.0
    assert feb["acumulado"] == 260.0       # 60 + 200


def test_flujo_previsto(datos):
    f = CF.flujo_previsto(E, desde="2026-03-01", hasta="2026-03-31", granularidad="mensual")
    mar = [x for x in f if x["periodo"] == "2026-03"][0]
    assert mar["entradas"] >= 500 and mar["salidas"] >= 150
    assert mar["neto"] == round(mar["entradas"] - mar["salidas"], 2)


def test_granularidades(datos):
    for g in ("diario", "semanal", "mensual", "anual"):
        f = CF.flujo(E, desde="2026-01-01", hasta="2026-12-31", granularidad=g, escenario="real")
        assert isinstance(f, list) and all("periodo" in x and "acumulado" in x for x in f)
    anual = CF.flujo_real(E, desde="2026-01-01", hasta="2026-12-31", granularidad="anual")
    assert [x for x in anual if x["periodo"] == "2026"][0]["neto"] == 260.0
