"""
BI Corporativo — OLAP: cubos, drill-down/up, slice, dice y comparativa temporal sobre el DW.
"""

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID

E = EMPRESA_DEFAULT_ID


@pytest.fixture
def datos(db):
    from src.services.bi_corp import dw
    for per, val in (("2098-01", 100), ("2098-02", 200), ("2098-03", 300)):
        dw.guardar_hecho("ventas", "facturacion", val, granularidad="mensual", periodo=per,
                         fecha=f"{per}-28", id_empresa=E, id_tienda=1)
        dw.guardar_hecho("compras", "gasto_total", val / 2, granularidad="mensual", periodo=per,
                         fecha=f"{per}-28", id_empresa=E, id_tienda=2)
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM dw_hechos WHERE periodo LIKE '2098-%%' AND id_empresa=%s", (E,))
        conn.commit()


def test_cubo_y_dice(db, datos):
    from src.services.bi_corp import olap
    c = olap.cubo(dimensiones=("dominio",), filtros={"periodo": ["2098-01", "2098-02", "2098-03"]}, id_empresa=E)
    doms = {f["dominio"]: float(f["valor"]) for f in c}
    assert doms.get("ventas") == 600.0   # 100+200+300
    d = olap.dice({"dominio": "ventas", "periodo": "2098-02"}, dimensiones=("metrica",), id_empresa=E)
    assert d and float(d[0]["valor"]) == 200.0


def test_drill_down_up(db, datos):
    from src.services.bi_corp import olap
    dd = olap.drill_down("dominio", filtros={"periodo": "2098-01"}, id_empresa=E)
    assert any(f.get("metrica") == "facturacion" for f in dd)
    du = olap.drill_up("metrica", filtros={"periodo": "2098-01"}, id_empresa=E)
    assert any("dominio" in f for f in du)


def test_slice_y_comparativa(db, datos):
    from src.services.bi_corp import olap
    s = olap.slice_("periodo", "2098-03", id_empresa=E)
    assert any(float(f["valor"]) == 300.0 for f in s if f.get("metrica") == "facturacion")
    cmp = olap.comparativa_temporal("facturacion", ["2098-01", "2098-03"], dominio="ventas", id_empresa=E)
    assert cmp["variacion_pct"] == 200.0   # de 100 a 300
