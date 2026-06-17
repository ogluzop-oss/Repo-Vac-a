"""Integración · FACeB2B preparado (C3.4.5): canal resoluble, no operativo todavía."""

import pytest

pytestmark = pytest.mark.db


def test_faceb2b_preparado_no_operativo():
    from src.services.fiscal.facturae.emisores.faceb2b import CanalFACeB2B
    c = CanalFACeB2B(config={"entorno": "preproduccion"})
    assert c.nombre == "faceb2b" and c.disponible() is False
    r = c.enviar(b"<x/>", {"numero": "1"}, {})
    assert r["ok"] is False and "faceb2b" in r["mensaje"].lower()
    assert "redsara" in c.endpoint({"entorno": "preproduccion"})


def test_canal_para_selecciona_por_nombre():
    from src.services.fiscal.facturae.servicio import canal_para
    from src.services.fiscal.facturae.emisores.face import CanalFACe
    from src.services.fiscal.facturae.emisores.faceb2b import CanalFACeB2B
    assert isinstance(canal_para({"canal": "face"}), CanalFACe)
    assert isinstance(canal_para({"canal": "faceb2b"}), CanalFACeB2B)
    assert isinstance(canal_para({}), CanalFACe)            # por defecto FACe
