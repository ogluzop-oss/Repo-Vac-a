"""Unit · registry de proveedores fiscales + huella encadenada (sin BD)."""

import pytest

pytestmark = pytest.mark.unit


def test_registry_descubre_simulado():
    from src.services.fiscal.registry import proveedores_registrados
    reg = proveedores_registrados()
    assert "simulado" in reg and "comun" in reg["simulado"]


def test_proveedor_para_territorio():
    from src.services.fiscal.factory import proveedor_para
    p = proveedor_para({"proveedor": "simulado", "territorio": "comun"})
    assert p is not None and p.nombre == "simulado"


def test_huella_encadena():
    from src.db import fiscal as F
    h1 = F.huella({"serie": "A", "numero": 1, "total": 10}, None)
    h2 = F.huella({"serie": "A", "numero": 2, "total": 20}, h1)
    assert h1 != h2 and len(h1) == 64
    # La huella depende del hash anterior (encadenado).
    assert F.huella({"serie": "A", "numero": 2, "total": 20}, "otro") != h2
