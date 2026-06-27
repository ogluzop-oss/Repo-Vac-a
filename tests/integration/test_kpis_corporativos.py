"""
BI Corporativo — KPIs corporativos unificados + rentabilidad por tienda (desde el DW).
"""
import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


@pytest.fixture
def datos(db):
    from src.services.bi_corp import dw
    dw.guardar_hecho("ventas", "facturacion", 5000, granularidad="mensual", periodo="2097-01",
                     fecha="2097-01-31", id_empresa=E, id_tienda=1)
    dw.guardar_hecho("ventas", "margen_bruto", 1500, granularidad="mensual", periodo="2097-01",
                     fecha="2097-01-31", id_empresa=E, id_tienda=1)
    dw.guardar_hecho("ventas", "facturacion", 3000, granularidad="mensual", periodo="2097-01",
                     fecha="2097-01-31", id_empresa=E, id_tienda=2)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dw_hechos WHERE periodo='2097-01' AND id_empresa=%s", (E,))
        conn.commit()


def test_valor_kpi(db, datos):
    from src.services.bi_corp import kpis_corp
    k = kpis_corp.valor_kpi("facturacion", periodo="2097-01", id_empresa=E)
    assert k["ok"] and k["valor"] == 8000.0   # 5000+3000
    assert kpis_corp.valor_kpi("desconocido", id_empresa=E)["ok"] is False


def test_cuadro_completo(db, datos):
    from src.services.bi_corp import kpis_corp
    cuadro = kpis_corp.cuadro(periodo="2097-01", id_empresa=E)
    assert len(cuadro) == len(kpis_corp.CATALOGO)
    assert all("codigo" in k for k in cuadro)


def test_rentabilidad_por_tienda(db, datos):
    from src.services.bi_corp import kpis_corp
    r = kpis_corp.rentabilidad_por("id_tienda", id_empresa=E)
    assert any(x["facturacion"] == 5000.0 for x in r)
