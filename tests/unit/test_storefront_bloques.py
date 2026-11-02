"""
Fase 4 e-commerce (Catálogo Web / Canal Web) — editor visual del storefront: renderizado por
secciones/bloques (`backend/storefront_bloques.py`) y el enganche en `storefront.pagina_home`
(Strangler: sin `tema_json` guardado, la home sigue siendo EXACTAMENTE la de siempre)."""

import pytest

from src.backend import storefront_bloques as sb

pytestmark = pytest.mark.db


def _ctx(eid="T-TEMA"):
    return {"eid": eid, "cfg": {"moneda": "EUR"}, "moneda": "EUR", "dest": [], "reco": [], "todos": []}


def test_bloque_por_defecto_trae_todos_los_campos_vacios():
    b = sb.bloque_por_defecto("hero")
    assert b["tipo"] == "hero"
    assert set(b["config"]) == {"titulo", "subtitulo", "texto_boton", "enlace_boton"}
    assert all(v == "" for v in b["config"].values())
    assert len(b["id"]) == 10


def test_bloque_por_defecto_tipo_desconocido_lanza():
    with pytest.raises(ValueError):
        sb.bloque_por_defecto("no_existe")


def test_render_hero_escapa_html_y_pinta_boton_solo_si_hay_texto():
    sin_boton = sb.renderizar_bloque(
        {"tipo": "hero", "config": {"titulo": "<script>x</script>", "subtitulo": "Bienvenido"}}, _ctx())
    assert "<script>" not in sin_boton and "&lt;script&gt;" in sin_boton
    assert "<a href" not in sin_boton

    con_boton = sb.renderizar_bloque(
        {"tipo": "hero", "config": {"titulo": "T", "subtitulo": "S",
                                    "texto_boton": "Comprar", "enlace_boton": "/tienda/T-TEMA"}}, _ctx())
    assert "<a href" in con_boton and "Comprar" in con_boton


def test_render_texto_sin_titulo_omite_el_h2():
    sin_titulo = sb.renderizar_bloque({"tipo": "texto", "config": {"texto": "Hola"}}, _ctx())
    assert "<h2>" not in sin_titulo and "Hola" in sin_titulo
    con_titulo = sb.renderizar_bloque({"tipo": "texto", "config": {"titulo": "Aviso", "texto": "Hola"}}, _ctx())
    assert "<h2>Aviso</h2>" in con_titulo


def test_render_grid_destacados_vacio_no_pinta_seccion():
    assert sb.renderizar_bloque({"tipo": "grid_destacados", "config": {}}, _ctx()) == ""


def test_render_separador_es_un_hr():
    assert "<hr" in sb.renderizar_bloque({"tipo": "separador", "config": {}}, _ctx())


def test_renderizar_bloque_tipo_desconocido_no_rompe_nunca():
    assert sb.renderizar_bloque({"tipo": "futuro_tipo_no_soportado", "config": {}}, _ctx()) == ""


def test_renderizar_bloque_config_mal_formada_no_rompe_nunca():
    # `config` es None en vez de dict: no debe lanzar — degrada a los campos vacíos.
    html = sb.renderizar_bloque({"tipo": "hero", "config": None}, _ctx())
    assert isinstance(html, str) and "<h1></h1>" in html


# ── Enganche en storefront.pagina_home (Strangler: cero regresión sin tema) ─────────────────────

def test_pagina_home_sin_tema_guardado_usa_el_layout_de_siempre(db, fab):
    from src.backend import storefront as sf
    fab.web(activa=1, nombre="Tienda Sin Tema", moneda="EUR")
    cod = fab.articulo(stock_total=5, precio=9.0, nombre="Agua")
    fab.producto_catalogo(cod, titulo_web="Agua Web", visible_web=1, destacado=1)
    html = sf.pagina_home(fab.EMP_DEFECTO)
    assert "Agua Web" in html and "Destacados" in html


def test_pagina_home_con_tema_guardado_usa_el_renderer_por_bloques(db, fab):
    import json
    from src.backend import storefront as sf
    from src.db import web_tienda
    fab.web(activa=1, nombre="Tienda Con Tema", moneda="EUR")
    tema = {"secciones": [
        {"id": "s1", "tipo": "hero", "config": {"titulo": "Bienvenidos", "subtitulo": "Lo mejor"}},
        {"id": "s2", "tipo": "grid_catalogo", "config": {}},
    ]}
    web_tienda.guardar_config(id_empresa=fab.EMP_DEFECTO, tema_json=json.dumps(tema))
    cod = fab.articulo(stock_total=3, precio=5.0, nombre="Pan")
    fab.producto_catalogo(cod, titulo_web="Pan Web", visible_web=1)
    html = sf.pagina_home(fab.EMP_DEFECTO)
    assert "Bienvenidos" in html and "Pan Web" in html
    assert "Lo mejor" in html


def test_pagina_home_con_tema_json_corrupto_degrada_al_layout_de_siempre(db, fab):
    from src.backend import storefront as sf
    from src.db import web_tienda
    fab.web(activa=1, nombre="Tienda Tema Roto", moneda="EUR")
    web_tienda.guardar_config(id_empresa=fab.EMP_DEFECTO, tema_json="{esto no es json valido")
    cod = fab.articulo(stock_total=1, precio=1.0, nombre="Sal")
    fab.producto_catalogo(cod, titulo_web="Sal Web", visible_web=1, destacado=1)
    html = sf.pagina_home(fab.EMP_DEFECTO)
    assert "Sal Web" in html and "Destacados" in html


def test_tema_json_con_secciones_vacias_degrada_al_layout_de_siempre(db, fab):
    import json
    from src.backend import storefront as sf
    from src.db import web_tienda
    fab.web(activa=1, nombre="Tienda Tema Vacio", moneda="EUR")
    web_tienda.guardar_config(id_empresa=fab.EMP_DEFECTO, tema_json=json.dumps({"secciones": []}))
    cod = fab.articulo(stock_total=1, precio=1.0, nombre="Miel")
    fab.producto_catalogo(cod, titulo_web="Miel Web", visible_web=1, destacado=1)
    html = sf.pagina_home(fab.EMP_DEFECTO)
    assert "Miel Web" in html and "Destacados" in html
