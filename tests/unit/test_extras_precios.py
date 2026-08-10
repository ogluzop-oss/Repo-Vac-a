"""
Tests · TPV · Precios editables de los extras (bolsas / sobres de regalo).
"""

import pytest

from src.services.tpv import extras_precios as EP

pytestmark = pytest.mark.db


def test_listar_los_cuatro_extras(db):
    items = EP.listar()
    assert {i["codigo"] for i in items} == set(EP.CODIGOS)
    assert all(i["precio"] >= 0 for i in items)


def test_guardar_y_obtener(db):
    orig = EP.obtener("BOLSA_GRANDE")
    try:
        ok, _ = EP.guardar({"BOLSA_GRANDE": "0,35", "SOBRE_REGALO_GRANDE": 1.75})  # tolera coma
        assert ok
        assert EP.obtener("BOLSA_GRANDE") == 0.35
        assert EP.obtener("SOBRE_REGALO_GRANDE") == 1.75
        # Código desconocido se ignora.
        ok2, _ = EP.guardar({"NO_EXISTE": 5.0})
        assert ok2 is False
    finally:
        EP.guardar({"BOLSA_GRANDE": orig, "SOBRE_REGALO_GRANDE": 1.00})
