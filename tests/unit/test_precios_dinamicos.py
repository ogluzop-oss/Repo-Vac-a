"""Motor de precios dinámicos + monitor de desvíos (Fase 3). (unit, sin db)

Cubre la lógica pura: detección de desvío (oportunidad/alerta/normal), PVP sugerido = coste*(1+margen) y
coste más bajo de la bolsa.
"""

from src.services.compras import precios_dinamicos as PD


def test_evaluar_desvio():
    assert PD.evaluar_desvio(8, 10) == "oportunidad"          # precio por debajo de la referencia
    assert PD.evaluar_desvio(12, 10, umbral_pct=10) == "alerta"   # +20% > umbral 10%
    assert PD.evaluar_desvio(10.5, 10, umbral_pct=10) == "normal"  # +5% dentro del umbral
    assert PD.evaluar_desvio(10, None) == "normal"            # sin referencia
    assert PD.evaluar_desvio(10, 0) == "normal"


def test_pvp_sugerido():
    assert PD.pvp_sugerido(10, 30) == 13.0
    assert PD.pvp_sugerido(8, 25) == 10.0
    assert PD.pvp_sugerido(0, 30) == 0.0


def test_coste_mas_bajo():
    assert PD.coste_mas_bajo([{"precio": 9}, {"precio": 7.5}, {"precio": 0}]) == 7.5
    assert PD.coste_mas_bajo([]) is None
