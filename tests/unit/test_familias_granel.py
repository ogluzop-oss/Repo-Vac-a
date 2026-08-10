"""
Tests · Báscula · Familias de productos a granel (taxonomía canónica + subfamilia).

Verifica la taxonomía única (`familias_granel`): 9 familias, subfamilias de Panes/Bollería, normalización
de categorías antiguas (texto libre → familia canónica) y el round-trip del servicio
(`bulk_products_service.guardar_producto`) persistiendo familia + subfamilia normalizadas.
"""

import pytest

from src.services.tpv import familias_granel as F


# ── Taxonomía (sin BD) ────────────────────────────────────────────────────────
def test_nueve_familias_canonicas():
    codigos = F.codigos()
    assert codigos == ["DULCES", "FRUTA", "VERDURA", "CARNICERIA", "PESCADERIA",
                       "PANES", "BOLLERIA", "LACTEOS", "FRUTOS_SECOS"]
    assert "OTROS" not in codigos                       # familia técnica: solo bajo demanda
    assert F.FAMILIA_OTROS in F.codigos(incluir_otros=True)


def test_subfamilias_panes_y_bolleria():
    assert [s["codigo"] for s in F.subfamilias("PANES")] == ["BARRAS", "HOGAZAS", "PANECILLOS"]
    assert [s["codigo"] for s in F.subfamilias("BOLLERIA")] == ["DULCE", "SALADA"]
    assert F.tiene_subfamilias("PANES") and F.tiene_subfamilias("BOLLERIA")
    # El resto de familias no tienen apartados.
    for c in ("DULCES", "FRUTA", "VERDURA", "CARNICERIA", "PESCADERIA", "LACTEOS", "FRUTOS_SECOS"):
        assert F.subfamilias(c) == []


def test_normalizar_legacy():
    assert F.normalizar("FRUTOS SECOS") == "FRUTOS_SECOS"
    assert F.normalizar("CARNE") == "CARNICERIA"
    assert F.normalizar("PESCADO") == "PESCADERIA"
    assert F.normalizar("QUESOS") == "LACTEOS"
    assert F.normalizar("FRESCOS") == "LACTEOS"        # cajón mixto → lácteos por defecto
    assert F.normalizar("GENERAL") == "OTROS"          # desconocido no se pierde
    assert F.normalizar(None) == "OTROS"
    assert F.normalizar("PANES") == "PANES"            # ya canónica


def test_venta_por_unidad_panes_y_bolleria():
    # Panes y Bollería se venden por UNIDADES; el resto por peso.
    assert F.vendido_por_unidad("PANES") and F.vendido_por_unidad("BOLLERIA")
    for c in ("DULCES", "FRUTA", "VERDURA", "CARNICERIA", "PESCADERIA", "LACTEOS", "FRUTOS_SECOS"):
        assert not F.vendido_por_unidad(c)
    # El flag también viaja en el descriptor de familias.
    porunidad = {f["codigo"] for f in F.familias() if f["por_unidad"]}
    assert porunidad == {"PANES", "BOLLERIA"}


def test_normalizar_subfamilia():
    # Familia con apartados: valida o cae a la primera.
    assert F.normalizar_subfamilia("PANES", "HOGAZAS") == "HOGAZAS"
    assert F.normalizar_subfamilia("PANES", "inexistente") == "BARRAS"
    assert F.normalizar_subfamilia("PANES", None) == "BARRAS"
    # Familia sin apartados: siempre vacío.
    assert F.normalizar_subfamilia("FRUTA", "BARRAS") == ""


# ── Servicio (round-trip con BD) ──────────────────────────────────────────────
@pytest.mark.db
def test_guardar_normaliza_familia_y_subfamilia(db):
    from src.services.tpv import bulk_products_service as B

    def _limpia():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM productos_granel WHERE nombre IN "
                        "('T-Baguette','T-Croissant','T-Queso Legacy')")
            c.commit()
    _limpia()
    try:
        # Pan con subfamilia → se persiste normalizada.
        ok, _ = B.guardar_producto("T-Baguette", 1.10, "🥖", "PANES", subfamilia="BARRAS")
        assert ok
        # Familia sin apartados: la subfamilia se descarta.
        ok, _ = B.guardar_producto("T-Croissant", 1.40, "🥐", "BOLLERIA", subfamilia="DULCE")
        assert ok
        # Categoría legacy de texto libre → familia canónica.
        ok, _ = B.guardar_producto("T-Queso Legacy", 9.0, "🧀", "FRESCOS")
        assert ok

        todos = {p["nombre"]: p for p in B.listar_todos()}
        assert todos["T-Baguette"]["categoria"] == "PANES"
        assert todos["T-Baguette"]["subfamilia"] == "BARRAS"
        assert todos["T-Croissant"]["categoria"] == "BOLLERIA"
        assert todos["T-Croissant"]["subfamilia"] == "DULCE"
        assert todos["T-Queso Legacy"]["categoria"] == "LACTEOS"
        assert todos["T-Queso Legacy"].get("subfamilia") in (None, "")
    finally:
        _limpia()
