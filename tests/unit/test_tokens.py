"""Unit · tokens JWT/refresh (firma/verificación, sin BD)."""

import datetime as dt

import pytest

from src.seguridad import tokens

pytestmark = pytest.mark.unit

_USR = {"id": 7, "id_empresa": "EMP-1", "tienda_id": 3, "perfil": "GERENTE", "nombre": "Ana"}


def test_access_roundtrip_y_claims():
    tok = tokens.emitir_access(_USR)
    datos = tokens.verificar(tok, tipo="access")
    assert datos and datos["sub"] == "7" and datos["empresa"] == "EMP-1"
    assert datos["rol"] == "GERENTE" and datos["tienda"] == 3


def test_tipo_incorrecto_rechaza():
    tok = tokens.emitir_access(_USR)
    assert tokens.verificar(tok, tipo="refresh") is None


def test_token_manipulado_invalido():
    tok = tokens.emitir_access(_USR)
    assert tokens.verificar(tok[:-3] + "abc") is None


def test_refresh_devuelve_jti_y_expira():
    tok, jti, expira = tokens.emitir_refresh(_USR)
    assert jti and expira > dt.datetime.now(dt.timezone.utc)
    assert tokens.verificar(tok, tipo="refresh")["jti"] == jti


def test_access_expirado():
    tok = tokens.emitir_access(_USR, minutos=-1)   # ya expirado
    assert tokens.verificar(tok) is None
