"""
Portal Empresa · página "Rappels acumulados" (`backend/portal_empresa_gestion.py::pagina_rappels`):
pedido explícito — se retira el texto explicativo y el recuadro gris que envolvía el título junto a
él, dejando el título como un `<h1>` libre por encima del resto del contenido.
"""

from src.backend.portal_empresa_gestion import pagina_rappels


def test_pagina_rappels_sin_texto_explicativo_ni_caja_en_el_titulo():
    html = pagina_rappels("tok123", proveedores=[], tramos_por_sum={}, progresos={},
                          liquidaciones=[], nombres_sum={})
    assert "sobre el gasto acumulado con un proveedor en una ventana de fechas" not in html
    assert "Precios por volumen" not in html
    assert "ejercicio fiscal" not in html
    assert "ya facturados" not in html
    # El título ya no va envuelto en la misma caja que el texto retirado.
    assert '<div class="card"><h1>Rappels acumulados</h1>' not in html
    assert "<h1>Rappels acumulados</h1>" in html


def test_pagina_rappels_sigue_renderizando_las_demas_secciones():
    html = pagina_rappels("tok123", proveedores=[], tramos_por_sum={}, progresos={},
                          liquidaciones=[], nombres_sum={})
    assert "Nuevo tramo" in html
    assert "Progreso por proveedor" in html
    assert "Tramos configurados" in html
    assert "Liquidaciones" in html
