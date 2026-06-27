"""Simulacion financiera What-If — impacto sobre beneficio/EBITDA/tesoreria/endeudamiento sin tocar datos."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_simular_impacto(db):
    from src.services.finanzas import simulacion
    r = simulacion.simular({"ventas": 20, "costes": -10, "tipos_interes": 1}, id_empresa=E)
    assert "impacto" in r and "beneficio" in r["impacto"]
    assert "simulado" in r["impacto"]["beneficio"] and "delta" in r["impacto"]["beneficio"]
    assert "ebitda" in r["impacto"] and "tesoreria" in r["impacto"]


def test_no_modifica_datos(db):
    from src.services.finanzas import simulacion
    base1 = simulacion._foto_base(E)
    simulacion.simular({"ventas": 50}, id_empresa=E)
    base2 = simulacion._foto_base(E)
    assert base1 == base2     # la simulacion no altera la foto real


def test_comparar_escenarios(db):
    from src.services.finanzas import simulacion
    esc = simulacion.comparar_escenarios(
        {"optimista": {"ventas": 15}, "pesimista": {"ventas": -15, "impagos": 10}}, id_empresa=E)
    assert "optimista" in esc and "pesimista" in esc
    assert esc["optimista"]["beneficio"]["simulado"] >= esc["pesimista"]["beneficio"]["simulado"]
