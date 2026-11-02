"""
Fase 1 (e-commerce PIM) — ampliaciones reales sobre BD, sin ninguna tabla/columna nueva:

- "Precio de comparación": reutiliza las columnas YA EXISTENTES `articulos.promo_activa`/
  `precio_promo` (ya LEÍDAS por `services.catalogo.service._precio_efectivo`, nunca antes
  escritas desde ninguna pantalla) — se expone aquí vía `articulos.actualizar_articulo`.
- Slug editable tras la creación (`catalogo.upsert_producto`).
- Variantes: `actualizar_variante` y alta masiva `crear_variantes_bulk` (matriz de
  combinaciones), sobre la tabla `catalogo_variantes` ya existente.
"""

import pytest

pytestmark = pytest.mark.db


def test_promo_activa_y_precio_promo_se_persisten_y_se_leen(db, fab):
    """El "precio de comparación" del encargo = el precio base (`articulos.precio`) tachado
    cuando hay una promoción activa — mecanismo YA existente, ahora escribible."""
    from src.db import articulos as art
    from src.db import catalogo as cat

    cod = fab.articulo(precio=29.90)
    pid = fab.producto_catalogo(cod, titulo_web="Producto promo")

    assert art.actualizar_articulo(cod, promo_activa=1, precio_promo=19.90) is True

    prod = cat.obtener_producto(id_producto=pid)
    assert prod["promo_activa"] in (1, True)
    assert float(prod["precio_promo"]) == 19.90
    assert float(prod["precio"]) == 29.90   # el precio base ("tachado") no se toca

    # Y el servicio de catálogo ya lo interpreta correctamente (precio efectivo = el de oferta).
    from src.services.catalogo import service as svc
    actual, base, en_promo = svc._precio_efectivo(prod)
    assert en_promo is True and actual == 19.90 and base == 29.90


def test_desactivar_promo_vuelve_al_precio_base(db, fab):
    from src.db import articulos as art
    from src.db import catalogo as cat
    from src.services.catalogo import service as svc

    cod = fab.articulo(precio=10.0)
    fab.producto_catalogo(cod)
    art.actualizar_articulo(cod, promo_activa=1, precio_promo=7.0)
    art.actualizar_articulo(cod, promo_activa=0)

    prod = cat.obtener_producto(codigo_articulo=cod)
    actual, base, en_promo = svc._precio_efectivo(prod)
    assert en_promo is False and actual == 10.0


def test_slug_editable_tras_la_creacion_y_normalizado(db, fab):
    from src.db import catalogo as cat

    cod = fab.articulo()
    pid = fab.producto_catalogo(cod, titulo_web="Mi Producto")
    slug_inicial = cat.obtener_producto(id_producto=pid)["slug"]
    assert slug_inicial   # autogenerado al crear

    cat.upsert_producto(cod, slug="  Nuevo SLUG Con Espacios  ")
    prod = cat.obtener_producto(id_producto=pid)
    assert prod["slug"] != slug_inicial
    assert " " not in prod["slug"]
    assert prod["slug"] == prod["slug"].lower()


def test_actualizar_variante_persiste_cambios(db, fab):
    from src.db import catalogo as cat

    cod = fab.articulo()
    pid = fab.producto_catalogo(cod)
    vid = cat.crear_variante(pid, sku="SKU-1", nombre="Talla M")
    fab.al_limpiar(lambda: cat.eliminar_variante(vid))

    ok = cat.actualizar_variante(vid, precio_dif=5.0, atributos={"Talla": "M", "Color": "Rojo"},
                                 visible=0)
    assert ok is True

    variantes = cat.listar_variantes(pid)
    v = next(x for x in variantes if x["id"] == vid)
    assert float(v["precio_dif"]) == 5.0
    assert v["atributos"] == {"Talla": "M", "Color": "Rojo"}   # decodificado, no JSON crudo
    assert v["visible"] in (0, False)


def test_variantes_sin_articulo_propio_no_tienen_stock(db, fab):
    from src.db import catalogo as cat

    cod = fab.articulo(stock_total=50)
    pid = fab.producto_catalogo(cod)
    vid = cat.crear_variante(pid, sku="SKU-SIN-STOCK", nombre="Única")
    fab.al_limpiar(lambda: cat.eliminar_variante(vid))

    v = next(x for x in cat.listar_variantes(pid) if x["id"] == vid)
    assert v["stock"] is None   # sin codigo_articulo propio -> no se inventa un stock


def test_variante_con_articulo_propio_expone_stock_real(db, fab):
    """Stock independiente por variante = vincularla a su PROPIO artículo (campo
    `codigo_articulo`, ya existente en el esquema) — el stock se lee del motor de stock real
    (`articulos.obtener_stock`), nunca de una columna de stock propia de `catalogo_variantes`
    (eso sí sería duplicar el motor de stock)."""
    from src.db import catalogo as cat

    cod_base = fab.articulo(nombre="Camiseta")
    cod_variante = fab.articulo(nombre="Camiseta Talla M", stock_total=12, stock_tienda=3)
    pid = fab.producto_catalogo(cod_base)
    vid = cat.crear_variante(pid, sku="CAM-M", nombre="Talla M", codigo_articulo=cod_variante)
    fab.al_limpiar(lambda: cat.eliminar_variante(vid))

    v = next(x for x in cat.listar_variantes(pid) if x["id"] == vid)
    assert v["stock"] == 15.0   # 12 (central) + 3 (tienda), vía obtener_stock real


def test_crear_variantes_bulk_matriz_completa(db, fab):
    """3 Tallas × 2 Colores = 6 variantes en una sola llamada atómica."""
    from src.db import catalogo as cat

    cod = fab.articulo()
    pid = fab.producto_catalogo(cod)
    combinaciones = [
        {"sku": f"T{i}", "nombre": f"Variante {i}", "precio_dif": i, "orden": i,
         "atributos": {"Talla": t, "Color": c}}
        for i, (t, c) in enumerate(
            (t, c) for t in ("S", "M", "L") for c in ("Rojo", "Azul"))
    ]
    res = cat.crear_variantes_bulk(pid, combinaciones)
    assert res == {"ok": True, "creadas": 6, "error": None}

    variantes = cat.listar_variantes(pid)
    fab.al_limpiar(lambda: [cat.eliminar_variante(v["id"]) for v in variantes])
    assert len(variantes) == 6
    assert {v["atributos"]["Talla"] for v in variantes} == {"S", "M", "L"}
    assert {v["atributos"]["Color"] for v in variantes} == {"Rojo", "Azul"}


def test_crear_variantes_bulk_es_atomico_ante_un_fallo(db, fab):
    """Si una combinación de la matriz es inválida, NINGUNA debe quedar creada (transacción real,
    no inserciones sueltas una a una)."""
    from src.db import catalogo as cat

    cod = fab.articulo()
    pid = fab.producto_catalogo(cod)
    combinaciones = [
        {"sku": "OK-1", "nombre": "Válida", "precio_dif": 1.0},
        {"sku": "MAL-2", "nombre": "Inválida", "precio_dif": "no-es-un-numero"},   # fuerza el fallo
    ]
    res = cat.crear_variantes_bulk(pid, combinaciones)
    assert res["ok"] is False
    assert cat.listar_variantes(pid) == []   # nada a medias


def test_crear_variantes_bulk_sin_combinaciones_degrada(db, fab):
    from src.db import catalogo as cat

    cod = fab.articulo()
    pid = fab.producto_catalogo(cod)
    assert cat.crear_variantes_bulk(pid, []) == {"ok": False, "creadas": 0, "error": "sin_combinaciones"}
