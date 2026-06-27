"""IA financiera — riesgo tesoreria, deteccion anomalias, prediccion impagos, recomendaciones (explicable)."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_riesgo_tesoreria(db):
    from src.services.finanzas import ia
    r = ia.riesgo_tesoreria(id_empresa=E)
    assert r["nivel"] in ("bajo", "medio", "alto", "critico")
    assert "explicacion" in r            # explicable, sin caja negra


def test_deteccion_anomalias(db):
    from src.services.finanzas import ia
    anom = ia.deteccion_anomalias(id_empresa=E)
    assert isinstance(anom, list)
    for a in anom:
        assert "explicacion" in a and "umbral" in a


def test_prediccion_impagos_y_recomendaciones(db):
    from src.services.finanzas import ia
    imp = ia.prediccion_impagos(id_empresa=E)
    assert isinstance(imp, list)
    recs = ia.recomendaciones(id_empresa=E)
    assert isinstance(recs, list)
    for r in recs:
        assert "accion" in r and "motivo" in r and "prioridad" in r


def test_dashboard_ejecutivo(db):
    from src.services.finanzas import dashboard
    p = dashboard.panel(id_empresa=E)
    assert {"tesoreria", "ratios", "deuda", "riesgo_tesoreria", "recomendaciones"} <= set(p.keys())
