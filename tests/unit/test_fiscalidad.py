"""Unit · desglose de IVA (lógica pura, sin BD)."""

import pytest

from src.utils import fiscalidad

pytestmark = pytest.mark.unit


def test_desglose_iva_21():
    d = fiscalidad.desglose_iva(121, tipo=21)
    assert d["base"] == 100.0 and d["cuota"] == 21.0 and d["total"] == 121.0


def test_desglose_iva_10():
    d = fiscalidad.desglose_iva(110, tipo=10)
    assert d["base"] == 100.0 and d["cuota"] == 10.0


def test_desglose_iva_sin_impuesto():
    d = fiscalidad.desglose_iva(50, tipo=0)
    assert d["base"] == 50.0 and d["cuota"] == 0.0


def test_iva_de_pais_es_positivo():
    assert fiscalidad.iva_de_pais("ES") > 0
