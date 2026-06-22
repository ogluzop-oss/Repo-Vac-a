"""
Tesorería · FASE 7 — Previsión financiera / liquidez (horizontes + alertas).
"""

import datetime as dt
import uuid

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T, vencimientos as V
from src.db.empresa import EMPRESA_DEFAULT_ID
from src.services.tesoreria import prevision_financiera as PF

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"


@pytest.fixture
def cuenta(db):
    cid = T.crear_cuenta("PF", IBAN, saldo_inicial=1000, id_empresa=E)
    yield cid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
        cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
        conn.commit()


def test_proyeccion_estructura_y_horizontes(cuenta):
    proy = PF.proyeccion_liquidez(E)
    assert proy["disponible_actual"] >= 1000
    hs = [p["horizonte_dias"] for p in proy["proyecciones"]]
    assert hs == [30, 90, 180, 365]
    for p in proy["proyecciones"]:
        esperado = round(p["disponible_inicial"] + (p["por_cobrar"] - p["comprometido"]) +
                         p["flujo_operativo_estimado"], 2)
        assert p["liquidez_estimada"] == esperado


def test_alerta_tension_por_vencimiento_pago(db, cuenta):
    # Un gran pago a 60 días debe tensar el horizonte de 90 días.
    f60 = (dt.date.today() + dt.timedelta(days=60)).strftime("%Y-%m-%d")
    vid = V.crear_vencimiento("PAGO", 100000, f60, origen="manual",
                              id_documento="PF" + uuid.uuid4().hex[:6], id_empresa=E)
    try:
        alertas = PF.alertas_liquidez(E, umbral=0.0)
        horizontes_alerta = {a["horizonte_dias"] for a in alertas}
        assert 90 in horizontes_alerta and 180 in horizontes_alerta and 365 in horizontes_alerta
        assert 30 not in horizontes_alerta        # el pago es a 60 días, no afecta a 30
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM vencimientos WHERE id=%s", (vid,))
            conn.commit()
