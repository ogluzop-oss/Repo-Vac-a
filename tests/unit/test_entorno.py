"""Unit · A5.1: secretos por entorno con fail-fast en producción."""

import pytest

from src.seguridad import entorno

pytestmark = pytest.mark.unit


def _limpiar(monkeypatch):
    for v in ("SMART_MANAGER_ENV", "SMART_MANAGER_JWT_SECRET",
              "SMART_MANAGER_SECRET_KEY", "SMART_MANAGER_SECRET_KEYS"):
        monkeypatch.delenv(v, raising=False)


def test_desarrollo_no_falla(monkeypatch):
    _limpiar(monkeypatch)
    # En dev no lanza (solo avisa), aunque falten secretos.
    assert entorno.validar_arranque_seguro() is False


def test_produccion_falla_sin_secretos(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("SMART_MANAGER_ENV", "prod")
    with pytest.raises(RuntimeError):
        entorno.validar_arranque_seguro()


def test_produccion_ok_con_secretos(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("SMART_MANAGER_ENV", "prod")
    monkeypatch.setenv("SMART_MANAGER_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("SMART_MANAGER_SECRET_KEY", "k" * 44)
    assert entorno.validar_arranque_seguro() is True


def test_tokens_no_usa_dev_secret_en_prod(monkeypatch):
    _limpiar(monkeypatch)
    monkeypatch.setenv("SMART_MANAGER_ENV", "prod")
    from src.seguridad import tokens
    # En produccion NUNCA debe devolverse el secreto de desarrollo (deriva de la
    # clave maestra o falla; jamas el fallback inseguro).
    try:
        s = tokens._secreto()
        assert s != "dev-insecure-jwt-secret-change-me"
    except RuntimeError:
        pass   # tambien es aceptable: fail-fast si no hay de donde derivar
