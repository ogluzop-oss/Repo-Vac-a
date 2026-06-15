"""Integración · storefront (Escenario B): consume el catálogo en vivo vía Flask."""

import pytest

pytestmark = pytest.mark.db


def _producto_demo(fab):
    cod = fab.articulo(stock_total=5, precio=12.0, nombre="Bebida")
    pid = fab.producto_catalogo(cod, titulo_web="Bebida Web", visible_web=1, destacado=1)
    from src.db import catalogo as cat
    return cat.obtener_producto(id_producto=pid)


def test_pagina_home_funcion_pura(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Demo", moneda="EUR")
    _producto_demo(fab)
    html = sf.pagina_home(fab.EMP_DEFECTO)
    assert "Bebida Web" in html and "Destacados" in html


def test_http_home_y_producto(db, fab):
    from src.backend.app import crear_app
    fab.web(activa=1, nombre="Tienda Demo")
    prod = _producto_demo(fab)
    cli = crear_app().test_client()
    r = cli.get(f"/tienda/{fab.EMP_DEFECTO}")
    assert r.status_code == 200 and b"Bebida Web" in r.data
    rp = cli.get(f"/tienda/{fab.EMP_DEFECTO}/producto/{prod['slug']}")
    assert rp.status_code == 200


def test_http_tienda_inactiva_404(db, fab):
    from src.backend.app import crear_app
    fab.web(activa=0)
    cli = crear_app().test_client()
    assert cli.get(f"/tienda/{fab.EMP_DEFECTO}").status_code == 404
