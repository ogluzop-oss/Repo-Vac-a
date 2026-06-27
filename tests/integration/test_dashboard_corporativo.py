"""
BI Corporativo — dashboard ejecutivo global, consolidacion multiempresa, benchmarking, export e IA.
"""
import os

import pytest

pytestmark = pytest.mark.db

from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


@pytest.fixture
def poblado(db):
    from src.services.bi_corp import dw
    dw.ejecutar_etl(granularidad="mensual", id_empresa=E)
    yield


def test_panel_global(db, poblado):
    from src.services.bi_corp import dashboard_corp
    p = dashboard_corp.panel(id_empresa=E, con_forecast=True, con_ia=True)
    assert "secciones" in p and len(p["secciones"]) == 12
    assert "kpis_estrategicos" in p and "forecast" in p and "ia_ejecutiva" in p


def test_consolidacion_multiempresa(db, poblado):
    from src.services.bi_corp import consolidacion
    c = consolidacion.consolidar(["facturacion"])
    assert "facturacion" in c and c["facturacion"]["num_empresas"] >= 1
    rk = consolidacion.ranking_empresas("facturacion")
    assert isinstance(rk, list)


def test_benchmarking(db, poblado):
    from src.services.bi_corp import benchmarking
    assert isinstance(benchmarking.ranking_clientes(id_empresa=E), list)
    assert isinstance(benchmarking.ranking_productos(id_empresa=E), list)
    with pytest.raises(ValueError):
        benchmarking.ranking("dim_mala", "facturacion", id_empresa=E)


def test_export_e_ia(db, poblado):
    from src.services.bi_corp import dashboard_corp, ia_ejecutiva
    inf = ia_ejecutiva.informe(id_empresa=E)
    assert inf["explicable"] is True and "resumen" in inf
    p = dashboard_corp.panel(id_empresa=E)
    r = dashboard_corp.exportar_panel(p, "csv", nombre="test_corp")
    assert r["ok"] and os.path.exists(r["ruta"])
    os.remove(r["ruta"])


def test_rbac_bi_corp(db):
    from src.services.seguridad import catalogo
    catalogo.sincronizar_catalogo()
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT codigo FROM permisos WHERE codigo IN ('bi_corp.ver','bi_corp.dw','bi_corp.ia')")
        enc = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    assert {"bi_corp.ver", "bi_corp.dw", "bi_corp.ia"} <= enc
