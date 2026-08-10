"""
IA/ML real por defecto: los caminos de predicción de dominio (`prediccion.ventas` y `prediccion.stock`) se
enrutan al motor REAL `forecasting` (Machine Learning con Prophet cuando hay datos suficientes; si no,
modelo estadístico/heurístico), etiquetando SIEMPRE el origen (modelo/tipo/es_ml). Este test usa una serie
corta → tier estadístico (rápido, sin invocar Prophet); el tier ML/Prophet se valida en test_forecasting.
"""

import datetime as dt

import pytest

from src.services.prediccion import stock as PS
from src.services.prediccion import ventas as PV


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _sembrar_ventas(fab, db, emp, cod, dias):
    hoy = dt.date.today()
    with db.obtener_conexion() as c, c.cursor() as cur:
        for i in range(dias):
            q = 10 + (i % 5)
            cur.execute("INSERT INTO ventas (fecha, codigo, cantidad, total, id_empresa) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        ((hoy - dt.timedelta(days=i)).isoformat(), cod, q, q, emp))
    fab._borrar("ventas", "codigo", cod)


def test_ventas_predecir_usa_motor_real(fab, emp, db):
    otra = fab.empresa("EMP ML VENTAS")   # aislada: solo sus ventas cuentan
    cod = fab.articulo(nombre="Producto ML", id_empresa=otra)
    _sembrar_ventas(fab, db, otra, cod, 20)   # 20 obs → tendencia lineal (estadística, sin Prophet)
    r = PV.predecir(otra)
    assert r["activo"] is True
    # etiquetado honesto del origen, proveniente de forecasting
    assert r["modelo"] in ("media_movil", "tendencia_lineal", "prophet")
    assert isinstance(r["es_ml"], bool) and r["tipo"] in ("heuristica", "estadistica", "ml")
    assert r["modelo"] == "tendencia_lineal" and r["es_ml"] is False   # 20 obs → estadística
    # 4 horizontes con valores derivados de la previsión ML/estadística
    assert len(r["predicciones"]) == 4
    valores = [p["valor"] for p in r["predicciones"]]
    assert all(v >= 0 for v in valores)
    assert valores[3] >= valores[0]   # el total del trimestre acumula más que el del día


def test_stock_predecir_incluye_origen(fab, emp, db):
    otra = fab.empresa("EMP ML STOCK")
    cod = fab.articulo(nombre="Producto ML2", id_empresa=otra)
    _sembrar_ventas(fab, db, otra, cod, 18)
    r = PS.predecir(otra)
    assert r["activo"] is True
    assert "es_ml" in r and r["modelo"] in ("media_movil", "tendencia_lineal", "prophet")
    dem = [p for p in r["predicciones"] if p["metrica"] == "demanda"]
    assert dem and dem[0]["valor"] >= 0


def test_sin_datos_no_es_ml(fab):
    otra = fab.empresa("EMP ML VACIA")     # sin ventas → nunca ML (honesto)
    r = PV.predecir(otra)
    assert r["es_ml"] is False and r["tipo"] in ("heuristica", "estadistica")
