"""
BI Corporativo — analitica predictiva: forecast por area con prediccion/confianza/tendencia/riesgo.
"""
import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


@pytest.fixture
def serie(db):
    from src.services.bi_corp import dw
    # Aisla la serie: elimina datos previos de ventas/facturacion de esta empresa.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dw_hechos WHERE id_empresa=%s AND dominio='ventas' AND metrica='facturacion'", (E,))
        conn.commit()
    for i, per in enumerate(("2096-01", "2096-02", "2096-03", "2096-04", "2096-05")):
        dw.guardar_hecho("ventas", "facturacion", 1000 + i * 200, granularidad="mensual", periodo=per,
                         fecha=f"{per}-28", id_empresa=E)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dw_hechos WHERE periodo LIKE '2096-%%' AND id_empresa=%s", (E,))
        conn.commit()


def test_forecast_area(db, serie):
    from src.services.bi_corp import forecast_corp
    f = forecast_corp.forecast("ventas", horizonte=3, id_empresa=E)
    assert f["ok"] and len(f["prediccion"]) == 3
    assert f["tendencia"] == "subiendo"            # serie creciente
    assert f["confianza"] in ("alta", "media", "baja")


def test_forecast_global(db, serie):
    from src.services.bi_corp import forecast_corp
    g = forecast_corp.forecast_global(id_empresa=E)
    assert "ventas" in g and g["ventas"]["ok"]


def test_forecast_area_desconocida(db):
    from src.services.bi_corp import forecast_corp
    assert forecast_corp.forecast("inexistente", id_empresa=E)["ok"] is False
