"""
Tests PCD · Etapa B · Fase B3: Catálogo Comercial Global.

Verifica que el catálogo COMPONE (no duplica) sobre PPL + multidivisa + fiscalidad: variantes con
delta de precio, impuestos por país, formato de moneda, contenido localizado (idioma), listado por
estado y reglas de visibilidad. Multiempresa. No muta el dominio ni el producto.
"""

import inspect

import pytest

EMP = "T-CAT-A"
COD = "CAT1"


@pytest.fixture()
def pub(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_catalogo_variantes WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        conn.commit()
    from src.services.comercio_digital import publicaciones as ppl
    pid = ppl.crear_publicacion(COD, contenido={"nombre": "Camiseta", "precio_escaparate": 100.0},
                                objetivo="vender", id_empresa=EMP)
    ppl.marcar_estado(pid, "PUBLICADA", id_empresa=EMP)
    yield pid
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_catalogo_variantes WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE v, i, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion LEFT JOIN cd_publicacion_i18n i "
                    "ON i.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        conn.commit()


def test_ficha_impuestos_por_pais(pub):
    from src.services.comercio_digital import catalogo as cat
    f_es = cat.ficha_comercial(pub, pais="ES", moneda="EUR", id_empresa=EMP)
    assert f_es["precio"]["neto"] == 100.0
    assert f_es["precio"]["iva_pct"] > 0                      # IVA del país aplicado
    assert f_es["precio"]["total"] == round(100.0 * (1 + f_es["precio"]["iva_pct"] / 100), 2)
    assert "€" in f_es["precio"]["total_fmt"]                 # formato multidivisa (EUR)


def test_variantes_con_delta(pub):
    from src.services.comercio_digital import catalogo as cat
    cat.agregar_variante(pub, "CAT1-L", atributos={"talla": "L"}, precio_delta=10, id_empresa=EMP)
    cat.agregar_variante(pub, "CAT1-XL", atributos={"talla": "XL"}, precio_delta=20, id_empresa=EMP)
    f = cat.ficha_comercial(pub, pais="ES", moneda="EUR", id_empresa=EMP)
    skus = {v["sku"]: v["precio"]["neto"] for v in f["variantes"]}
    assert skus["CAT1-L"] == 110.0 and skus["CAT1-XL"] == 120.0   # delta aplicado sobre el base


def test_localizacion_idioma(pub):
    from src.services.comercio_digital import catalogo as cat, publicaciones as ppl
    ppl.set_i18n(pub, "en", {"contenido": {"nombre": "T-Shirt"}}, id_empresa=EMP)
    # Localiza por idioma incluso con país (fallback de región (idioma, pais) → (idioma, '')).
    assert cat.ficha_comercial(pub, pais="ES", idioma="en", id_empresa=EMP)["contenido"]["nombre"] == "T-Shirt"
    assert cat.ficha_comercial(pub, id_empresa=EMP)["contenido"]["nombre"] == "Camiseta"


def test_moneda_formato(pub):
    from src.services.comercio_digital import catalogo as cat
    f_usd = cat.ficha_comercial(pub, pais="ES", moneda="USD", id_empresa=EMP)
    assert f_usd["moneda"] == "USD" and "$" in f_usd["precio"]["total_fmt"]


def test_catalogo_lista_publicadas(pub):
    from src.services.comercio_digital import catalogo as cat
    fichas = cat.catalogo(EMP, pais="ES", moneda="EUR")
    assert any(f["id_publicacion"] == pub for f in fichas)


def test_catalogo_compone_no_duplica():
    from src.services.comercio_digital import catalogo as cat
    src = inspect.getsource(cat)
    # Reutiliza PPL + capacidades divisas/fiscalidad; no reimplementa IVA ni formato de moneda.
    assert "preparar_para_canal" in src and "capabilities" in src
    for prohibido in ("def iva_de_pais", "def formatear", "CREATE TABLE"):
        assert prohibido not in src
    d = cat.descriptor()
    assert d["es_motor"] is False and d["muta_dominio"] is False
    assert set(d["compone_sobre"]) >= {"product_publication_layer", "divisas", "fiscalidad"}


def test_aislamiento_multiempresa(pub):
    from src.services.comercio_digital import catalogo as cat
    cat.agregar_variante(pub, "X", precio_delta=5, id_empresa=EMP)
    assert cat.variantes(pub, id_empresa=EMP)                 # EMP ve su variante
    assert cat.variantes(pub, id_empresa="T-CAT-OTRA") == []  # otra empresa no
