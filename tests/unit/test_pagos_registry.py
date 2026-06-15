"""Unit · registros extensibles de pasarelas y verificadores de webhook."""

import pytest

pytestmark = pytest.mark.unit


def test_pasarelas_registradas():
    from src.services.tpv.pagos.registry import pasarelas_registradas, proveedor_por_defecto
    reg = pasarelas_registradas()
    assert set(reg) >= {"redsys", "stripe", "paypal", "simulado"}
    # Redsys es la recomendada/por defecto para el mercado principal.
    assert proveedor_por_defecto() == "redsys"
    assert reg["redsys"]["recomendada"] is True
    # …y aparece la primera (orden recomendada→orden).
    assert next(iter(reg)) == "redsys"


def test_factory_resuelve_por_nombre():
    from src.services.tpv.pagos.factory import pasarela_para
    assert pasarela_para({"proveedor": "stripe"}).nombre == "stripe"
    # Proveedor desconocido cae a la recomendada (redsys).
    assert pasarela_para({"proveedor": "noexiste"}).nombre == "redsys"


def test_verificadores_webhook_registrados():
    from src.services.tpv.pagos.webhooks import verificadores_registrados
    assert verificadores_registrados() == ["paypal", "redsys", "stripe"]
