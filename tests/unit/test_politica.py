"""Unit · política de contraseñas."""

import pytest

from src.seguridad import politica

pytestmark = pytest.mark.unit


def test_longitud_minima():
    assert politica.validar("Corta_1")[0] is False
    assert politica.validar("Contrasena_Larga_123")[0] is True


def test_rechaza_comunes():
    assert politica.validar("administrador")[0] is False


def test_exige_variedad():
    assert politica.validar("aaaaaaaaaaaa")[0] is False        # un solo tipo
    assert politica.validar("aaaaaaaaaaa1")[0] is True         # dos tipos


def test_sin_espacios_extremos():
    assert politica.validar("  ClaveLarga123  ")[0] is False
