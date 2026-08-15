"""Bolsa de proveedores (Fase 1 · modelo) — tarifas por unidad de medida + comparativa por artículo.

Reutiliza `proveedor_precios_negociados` (migr 0103) + `unidad_medida` (migr 0197). Verifica que
`bolsa_precios(articulo)` lista las tarifas vigentes de todos los proveedores, ordena por precio neto y
filtra por proveedor / unidad de medida.
"""

import pytest

from src.db import proveedores as PROV
from src.services.compras import proveedores_pro as PP

pytestmark = pytest.mark.db


def _limpia(db, id_empresa):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE pn FROM proveedor_precios_negociados pn WHERE pn.id_empresa=%s", (id_empresa,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (id_empresa,))
        conn.commit()


def test_bolsa_precios_ordena_y_filtra(db, fab):
    emp = fab.empresa("EMP bolsa")
    fab.al_limpiar(lambda: _limpia(db, emp))

    p1 = PROV.crear_proveedor("Proveedor Caro", id_empresa=emp)
    p2 = PROV.crear_proveedor("Proveedor Barato", id_empresa=emp)
    p3 = PROV.crear_proveedor("Proveedor Medio", id_empresa=emp)
    art = "ART-BOLSA-1"

    # tarifas por UNIDAD de los 3 proveedores (con un descuento en el caro para probar precio neto)
    PP.set_precio_negociado(p1, art, 10.0, descuento=10, unidad_medida="unidad", id_empresa=emp)  # neto 9.0
    PP.set_precio_negociado(p2, art, 7.5, unidad_medida="unidad", id_empresa=emp)                  # neto 7.5
    PP.set_precio_negociado(p3, art, 8.0, unidad_medida="unidad", id_empresa=emp)                  # neto 8.0
    # una tarifa por CAJA del barato (otra unidad de medida)
    PP.set_precio_negociado(p2, art, 80.0, unidad_medida="caja", id_empresa=emp)

    # ── por defecto: solo compara y ordena por precio neto ascendente ──
    bolsa = PP.bolsa_precios(art, id_empresa=emp)
    assert len(bolsa) == 4
    netos = [float(r["precio_neto"]) for r in bolsa]
    assert netos == sorted(netos)                        # ascendente
    # el más barato por unidad es el "Proveedor Barato" (7.5) — primero de los de unidad
    unidades = [r for r in bolsa if r["unidad_medida"] == "unidad"]
    assert unidades[0]["proveedor"] == "Proveedor Barato" and float(unidades[0]["precio_neto"]) == 7.5
    # precio neto del caro = 10 * (1 - 10/100) = 9.0
    caro = [r for r in bolsa if r["proveedor"] == "Proveedor Caro"][0]
    assert float(caro["precio_neto"]) == 9.0

    # ── descendente ──
    desc = PP.bolsa_precios(art, id_empresa=emp, descendente=True)
    assert [float(r["precio_neto"]) for r in desc] == sorted(netos, reverse=True)

    # ── filtro por proveedor ──
    solo_p2 = PP.bolsa_precios(art, id_empresa=emp, id_proveedor=p2)
    assert {r["id_proveedor"] for r in solo_p2} == {p2} and len(solo_p2) == 2   # unidad + caja

    # ── filtro por unidad de medida ──
    cajas = PP.bolsa_precios(art, id_empresa=emp, unidad_medida="caja")
    assert len(cajas) == 1 and cajas[0]["unidad_medida"] == "caja" and float(cajas[0]["precio"]) == 80.0
