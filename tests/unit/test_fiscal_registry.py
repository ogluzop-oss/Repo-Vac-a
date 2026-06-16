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


def test_serie_efectiva_estrategias():
    from src.db import fiscal as F
    base = {"serie": "A"}
    # empresa → serie base; ignora tienda/caja.
    assert F.serie_efectiva({**base, "serie_por": "empresa"}, id_tienda=3, id_caja="CAJA-02") == "A"
    # tienda → sufijo por tienda.
    assert F.serie_efectiva({**base, "serie_por": "tienda"}, id_tienda=3) == "A-T3"
    # caja → sufijo por caja (normaliza 'CAJA-02' → 'CAJA02').
    assert F.serie_efectiva({**base, "serie_por": "caja"}, id_tienda=3, id_caja="CAJA-02") == "A-CCAJA02"


def test_serie_efectiva_degradacion_segura():
    from src.db import fiscal as F
    # tienda única sin id_tienda → cae a la serie base (no rompe numeración).
    assert F.serie_efectiva({"serie": "A", "serie_por": "tienda"}, id_tienda=None) == "A"
    # caja sin id_caja pero con tienda → cae a serie por tienda.
    assert F.serie_efectiva({"serie": "A", "serie_por": "caja"}, id_tienda=7, id_caja=None) == "A-T7"
    # default (sin serie_por) = tienda.
    assert F.serie_efectiva({"serie": "B"}, id_tienda=2) == "B-T2"
