"""Integración · login y migración de hash en el acceso (sin romper usuarios)."""

import hashlib

import pytest

pytestmark = pytest.mark.db


def _hash_almacenado(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT password FROM usuarios WHERE id=%s", (uid,))
        return cur.fetchone()[0]


def test_login_argon2(db, fab):
    from src.db import usuario as U
    u = fab.usuario(perfil="GERENTE", password="Gerente_Clave_123")
    res = U.validar_login("GERENTE", "Gerente_Clave_123")
    assert res and res["id"] == u["id"]
    assert U.validar_login("GERENTE", "mala") is None


def test_login_legado_se_migra_a_argon2(db, fab):
    from src.db import usuario as U
    u = fab.usuario(perfil="ADMINISTRADOR", password="Admin_Legado_123", hash_legado=True)
    # El hash inicial es SHA-256 (64 hex).
    assert len(_hash_almacenado(db, u["id"])) == 64
    # Login correcto → autentica y rehashea a Argon2id.
    assert U.validar_login("ADMINISTRADOR", "Admin_Legado_123")
    assert _hash_almacenado(db, u["id"]).startswith("$argon2id$")
    # Sigue funcionando tras la migración.
    assert U.validar_login("ADMINISTRADOR", "Admin_Legado_123")


def test_login_empleado_por_nombre(db, fab):
    from src.db import usuario as U
    u = fab.usuario(nombre="EMP_TEST_1", password="Empleado_Clave_123")
    res = U.validar_login_empleado("emp_test_1", "Empleado_Clave_123")
    assert res and res["id"] == u["id"]


def test_pin_fichaje_dual(db, fab):
    from src.db import usuario as U
    # Empleado con PIN legado (SHA-256) y otro con Argon2.
    u1 = fab.usuario(nombre="PINUSER_LEG", password="4729", hash_legado=True)
    u2 = fab.usuario(nombre="PINUSER_NEW", password="8351")
    r1 = U.validar_pin_fichaje("4729")
    assert r1 and r1["id"] == u1["id"]
    # El PIN legado se migró a Argon2 tras validarlo.
    assert _hash_almacenado(db, u1["id"]).startswith("$argon2id$")
    r2 = U.validar_pin_fichaje("8351")
    assert r2 and r2["id"] == u2["id"]
