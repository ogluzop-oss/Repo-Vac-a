"""Integración · aislamiento multi-tenant: lo creado en una empresa no es visible
desde otra (catálogo y storefront)."""

import pytest

pytestmark = pytest.mark.db


def test_catalogo_aislado_por_empresa(db, fab):
    from src.db import catalogo as cat
    emp_b = fab.empresa("EMP B")
    cod_b = fab.articulo(id_empresa=emp_b, nombre="Solo B")
    fab.producto_catalogo(cod_b, id_empresa=emp_b, titulo_web="Producto B", visible_web=1)
    # Desde la empresa por defecto (A) no debe aparecer el producto de B.
    cods_a = {p.get("codigo_articulo") for p in cat.listar_productos(id_empresa=fab.EMP_DEFECTO)}
    cods_b = {p.get("codigo_articulo") for p in cat.listar_productos(id_empresa=emp_b)}
    assert cod_b in cods_b and cod_b not in cods_a


def test_storefront_aislado_por_empresa(db, fab):
    from src.backend.app import crear_app
    emp_b = fab.empresa("EMP B web")
    fab.web(id_empresa=emp_b, activa=1, nombre="Tienda B")
    cod_b = fab.articulo(id_empresa=emp_b, nombre="Art B")
    fab.producto_catalogo(cod_b, id_empresa=emp_b, titulo_web="Producto B Web", visible_web=1)
    # La web de A (por defecto) está inactiva → 404; la de B responde con SU producto.
    cli = crear_app().test_client()
    rb = cli.get(f"/tienda/{emp_b}")
    assert rb.status_code == 200 and b"Producto B Web" in rb.data
    ra = cli.get(f"/tienda/{fab.EMP_DEFECTO}")
    assert ra.status_code == 404 or b"Producto B Web" not in ra.data
