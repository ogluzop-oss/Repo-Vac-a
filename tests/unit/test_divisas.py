"""Unit · formato de divisas (lógica pura, sin BD)."""

import pytest

from src.utils import divisas

pytestmark = pytest.mark.unit


def test_simbolo_es_cadena():
    assert isinstance(divisas.simbolo("EUR"), str) and divisas.simbolo("EUR")


def test_formatear_incluye_importe():
    s = divisas.formatear(1234.5, code="EUR")
    assert isinstance(s, str) and "1" in s and "234" in s.replace(".", "").replace(",", "")


def test_formatear_sin_simbolo():
    con = divisas.formatear(10, code="USD", con_simbolo=True)
    sin = divisas.formatear(10, code="USD", con_simbolo=False)
    assert len(sin) <= len(con)


def test_monedas_soportadas_incluye_eur():
    codigos = {m.get("code") if isinstance(m, dict) else m for m in divisas.monedas_soportadas()}
    assert "EUR" in codigos
