"""Unit · hashing Argon2id + migración desde SHA-256 (sin BD)."""

import hashlib

import pytest

from src.seguridad import passwords as pw

pytestmark = pytest.mark.unit


def test_hash_es_argon2id():
    h = pw.hash_password("Secreta_Larga_123")
    assert h.startswith("$argon2id$") and not pw.es_hash_legado(h)


def test_verifica_correcta_e_incorrecta():
    h = pw.hash_password("clave-correcta-larga")
    assert pw.verificar("clave-correcta-larga", h)[0] is True
    assert pw.verificar("otra", h)[0] is False


def test_detecta_y_migra_hash_legado():
    legado = hashlib.sha256("vieja123456".encode()).hexdigest()
    assert pw.es_hash_legado(legado)
    ok, nuevo = pw.verificar("vieja123456", legado)
    assert ok is True
    # Al validar un hash legado correcto, propone un hash nuevo Argon2id (rehash).
    assert nuevo and nuevo.startswith("$argon2id$")


def test_legado_incorrecto_no_migra():
    legado = hashlib.sha256("vieja".encode()).hexdigest()
    ok, nuevo = pw.verificar("incorrecta", legado)
    assert ok is False and nuevo is None


def test_argon2_correcto_no_pide_rehash():
    h = pw.hash_password("clave-larga-suficiente")
    ok, nuevo = pw.verificar("clave-larga-suficiente", h)
    assert ok is True and nuevo is None
