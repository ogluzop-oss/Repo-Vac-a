"""KPIs financieros — EBITDA/EBIT/ratios derivados de balance/PyG/tesoreria/deuda."""
import pytest

pytestmark = pytest.mark.db
from src.db.empresa import EMPRESA_DEFAULT_ID
E = EMPRESA_DEFAULT_ID


def test_ratios_completos(db):
    from src.services.finanzas import ratios
    k = ratios.calcular(id_empresa=E)
    esperados = {"ebitda", "ebit", "beneficio_neto", "liquidez_corriente", "prueba_acida",
                 "endeudamiento", "solvencia", "roa", "roe", "margen_neto", "margen_operativo",
                 "rotacion_activos", "periodo_medio_cobro_dias", "periodo_medio_pago_dias",
                 "cash_conversion_cycle", "deuda_viva"}
    assert esperados <= set(k.keys())


def test_ratios_no_lanzan(db):
    from src.services.finanzas import ratios
    # Debe degradar sin excepciones aunque falten datos contables.
    k = ratios.calcular(anio=2099, id_empresa=E)
    assert isinstance(k, dict) and "ebitda" in k
