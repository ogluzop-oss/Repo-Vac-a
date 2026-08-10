"""
Consolidación de la categorización de producto en la FAMILIA (fuente única `familias_producto`). El flag
`restringida` marca ventas con verificación de edad (alcohol/tabaco…) que consume el autocobro; los antiguos
campos libres `articulos.seccion`/`categoria` YA NO se usan (evita información desfasada). Migr 0187.
"""

import pytest

from src.db import familias as F
from src.services.tpv import self_checkout_service as SC


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def test_flag_restringida_persiste(emp, fab):
    fid = F.crear_familia("Bodega", restringida=True, id_empresa=emp)
    assert fid
    fab._borrar("familias_producto", "id", fid)
    assert int(F.obtener_familia(fid, emp)["restringida"]) == 1
    F.actualizar_familia(fid, id_empresa=emp, restringida=0)
    assert int(F.obtener_familia(fid, emp)["restringida"]) == 0


def test_restringido_por_flag_de_familia():
    # familia marcada como restringida → restringido aunque el nombre no lo diga (sin BD)
    assert SC.es_producto_restringido({"familia_restringida": True, "nombre": "Producto X"}) is True


def test_restringido_por_nombre_de_familia():
    assert SC.es_producto_restringido({"familia_nombre": "ALCOHOL", "nombre": "Zumo"}) is True


def test_restringido_por_nombre_de_producto():
    assert SC.es_producto_restringido({"nombre": "VINO Tinto Reserva"}) is True


def test_seccion_categoria_ya_no_restringen():
    # los antiguos campos libres NO deben restringir (fuente única = familia)
    assert SC.es_producto_restringido({"seccion": "ALCOHOL", "categoria": "TABACO",
                                       "nombre": "Genérico"}) is False


def test_resuelve_restriccion_por_id_familia(emp, fab):
    fid = F.crear_familia("Tabaquería", restringida=True, id_empresa=emp)
    fab._borrar("familias_producto", "id", fid)
    assert SC.es_producto_restringido({"id_familia": fid, "id_empresa": emp,
                                       "nombre": "Producto genérico"}) is True
