"""Integración · catálogo: árbol de categorías, overlay y doble vista (pública/operativa)."""

import pytest

pytestmark = pytest.mark.db


def test_arbol_categorias(db, fab):
    from src.db import catalogo as cat
    padre = fab.categoria("Padre")
    hija = fab.categoria("Hija", parent_id=padre)
    arbol = cat.arbol_categorias()
    nodo = next((n for n in arbol if n["id"] == padre), None)
    assert nodo and any(h["id"] == hija for h in nodo["hijos"])


def test_eliminar_categoria_recuelga_hijas(db, fab):
    from src.db import catalogo as cat
    padre = cat.crear_categoria("P borrar")
    hija = cat.crear_categoria("H sube", parent_id=padre)
    fab.al_limpiar(lambda: cat.eliminar_categoria(hija))
    assert cat.eliminar_categoria(padre)
    fila = [c for c in cat.listar_categorias() if c["id"] == hija]
    assert fila and fila[0]["parent_id"] is None


def test_overlay_y_doble_vista(db, fab):
    from src.services import catalogo as svc
    cod = fab.articulo(stock_total=5, precio=9.0, nombre="Cosa")
    pid = fab.producto_catalogo(cod, titulo_web="Cosa Web", visible_web=1, destacado=1)
    pub = svc.producto(id_producto=pid, interno=False)
    opv = svc.producto(id_producto=pid, interno=True)
    # La vista pública NO expone stock ni datos internos.
    assert not any("stock" in k for k in pub) and "codigo_articulo" not in pub
    # La operativa sí.
    assert opv["stock_vendible"] == 5 and opv["codigo_articulo"] == cod


def test_vista_publica_oculta_no_visibles(db, fab):
    from src.services import catalogo as svc
    cod = fab.articulo()
    pid = fab.producto_catalogo(cod, visible_web=0)
    assert svc.producto(id_producto=pid, interno=False) is None      # oculto al público
    assert svc.producto(id_producto=pid, interno=True) is not None   # visible para gestión
