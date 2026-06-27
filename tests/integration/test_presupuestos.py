"""Presupuestos financieros — versiones, escenarios, real-vs-presupuesto, desviaciones, forecast."""
import uuid
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


@pytest.fixture
def limpia(db):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("presupuesto_lineas", "presupuesto_escenarios", "presupuesto_versiones",
                  "presupuestos_financieros"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (E,))
        conn.commit()


def test_presupuesto_y_escenarios(db, limpia):
    from src.services.finanzas import presupuestos as P
    pid = P.crear_presupuesto(f"PP_{uuid.uuid4().hex[:4]}", "Anual", 2026, id_empresa=E)
    assert pid
    P.añadir_linea(pid, "ingreso", "Ventas", 1, 100000, id_empresa=E)
    P.añadir_linea(pid, "gasto", "Compras", 1, 60000, id_empresa=E)
    base = P.presupuestado(pid, id_empresa=E)
    assert base["ingreso"] == 100000 and base["resultado"] == 40000
    pes = P.presupuestado(pid, escenario="pesimista", id_empresa=E)
    assert pes["ingreso"] == 90000     # factor 0.9 sobre base
    with pytest.raises(ValueError):
        P.añadir_linea(pid, "zzz", "x", 1, 1, id_empresa=E)


def test_real_vs_presupuesto_y_forecast(db, limpia):
    from src.services.finanzas import presupuestos as P
    pid = P.crear_presupuesto(f"PP_{uuid.uuid4().hex[:4]}", "Anual", 2026, id_empresa=E)
    P.añadir_linea(pid, "ingreso", "Ventas", 1, 120000, id_empresa=E)
    cmp = P.real_vs_presupuesto(pid, id_empresa=E)
    assert "desviacion" in cmp["ingreso"] and "desviacion_pct" in cmp["ingreso"]
    fc = P.forecast_cierre(pid, periodos_transcurridos=6, id_empresa=E)
    assert "ingreso" in fc and "resultado" in fc


def test_versiones(db, limpia):
    from src.services.finanzas import presupuestos as P
    pid = P.crear_presupuesto(f"PP_{uuid.uuid4().hex[:4]}", "Anual", 2026, id_empresa=E)
    P.añadir_linea(pid, "gasto", "G", 1, 1000, id_empresa=E)
    v2 = P.nueva_version(pid, nota="rev", copiar_de=1, id_empresa=E)
    assert v2 == 2
    assert P.presupuestado(pid, version=2, id_empresa=E)["gasto"] == 1000
