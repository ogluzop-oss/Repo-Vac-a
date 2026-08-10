"""
Tests · Autocobro · Capa 1 (física de seguridad): peso esperado + tolerancia POR ARTÍCULO.

Verifica que `BaggingAreaController` usa el peso/tolerancia reales de la ficha (respetando tolerancias
más estrictas y sin que el suelo global las afloje), que suma tolerancias entre artículos y que el
artículo sin datos mantiene el comportamiento anterior (suelo global). Además, la API de master data
`db.articulos.guardar/obtener_fisica_seguridad`.
"""

import pytest

from src.services.tpv.self_checkout_service import (
    ESTADO_BLOQUEADO,
    ESTADO_OK,
    TOLERANCIA_KG,
    BaggingAreaController,
)


def test_tolerancia_por_articulo_estricta_se_respeta():
    c = BaggingAreaController()
    pasta = {"peso_unitario": 0.5, "tolerancia_peso": 0.015}
    c.al_escanear(pasta)
    assert c.peso_esperado == 0.5
    assert c.tolerancia_efectiva == 0.015              # NO la afloja el suelo global (0.06)
    assert c.verificar(0.510)[0] == ESTADO_OK          # +10 g dentro de ±15 g
    assert c.verificar(0.530)[0] == ESTADO_BLOQUEADO   # +30 g fuera → artículo sin escanear


def test_articulo_sin_datos_usa_suelo_global():
    c = BaggingAreaController()
    c.al_escanear({"codigo": "X"})                     # sin peso/tolerancia
    assert c.peso_esperado == BaggingAreaController.peso_articulo({})
    assert c.tolerancia_efectiva == TOLERANCIA_KG      # comportamiento anterior preservado


def test_tolerancias_se_suman_entre_articulos():
    c = BaggingAreaController()
    c.al_escanear({"peso_unitario": 0.5, "tolerancia_peso": 0.015})
    c.al_escanear({"peso_unitario": 0.2, "tolerancia_peso": 0.010})
    assert c.peso_esperado == 0.7
    assert c.tolerancia_efectiva == 0.025
    c.al_eliminar({"peso_unitario": 0.2, "tolerancia_peso": 0.010})
    assert c.peso_esperado == 0.5 and c.tolerancia_efectiva == 0.015


@pytest.mark.db
def test_api_fisica_seguridad(db):
    from src.db.articulos import guardar_fisica_seguridad, obtener_fisica_seguridad
    cod = "T-FISICA-1"
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("INSERT IGNORE INTO articulos (codigo, nombre, precio) VALUES (%s,'Pasta',1.0)", (cod,))
        c.commit()
    try:
        ok, _ = guardar_fisica_seguridad(cod, "0,500", "0,015")   # tolera coma decimal
        assert ok
        assert obtener_fisica_seguridad(cod) == {"peso_unitario": 0.5, "tolerancia_peso": 0.015}
        # obtener_articulo (SELECT *) devuelve las columnas → alimenta el bagging.
        from src.db.conexion import obtener_articulo
        art = obtener_articulo(cod)
        assert float(art["peso_unitario"]) == 0.5 and float(art["tolerancia_peso"]) == 0.015
        # Vaciar a NULL usa de nuevo los valores por defecto del motor.
        ok2, _ = guardar_fisica_seguridad(cod, "", "")
        assert ok2 and obtener_fisica_seguridad(cod) == {"peso_unitario": None, "tolerancia_peso": None}
        # Código inexistente → error controlado.
        assert guardar_fisica_seguridad("NO-EXISTE-XYZ", 0.5, 0.01)[0] is False
    finally:
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM articulos WHERE codigo=%s", (cod,))
            c.commit()
