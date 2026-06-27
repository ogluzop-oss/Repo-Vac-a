"""
BI Corporativo — anomalias y alertas inteligentes sobre el DW.
"""
import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


@pytest.fixture
def caida(db):
    from src.services.bi_corp import dw
    # ventas estables y caida brusca el ultimo periodo
    for per, val in (("2095-01", 1000), ("2095-02", 1000), ("2095-03", 1000), ("2095-04", 400)):
        dw.guardar_hecho("ventas", "facturacion", val, granularidad="mensual", periodo=per,
                         fecha=f"{per}-28", id_empresa=E)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dw_hechos WHERE periodo LIKE '2095-%%' AND id_empresa=%s", (E,))
        conn.commit()


def test_detecta_caida_ventas(db, caida):
    from src.services.bi_corp import alertas
    al = alertas.detectar(id_empresa=E)
    assert any(a["tipo"] == "caida_ventas" for a in al)


def test_emitir_alertas(db, caida):
    from src.services.bi_corp import alertas
    r = alertas.emitir_alertas(id_empresa=E)
    assert r["detectadas"] >= 1 and r["emitidas"] >= 1
