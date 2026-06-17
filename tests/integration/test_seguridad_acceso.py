"""Integración · bloqueo temporal por intentos fallidos."""

import pytest

pytestmark = pytest.mark.db


def _campos(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT intentos_fallidos, bloqueado_hasta FROM usuarios WHERE id=%s", (uid,))
        return cur.fetchone()


def test_bloqueo_tras_5_fallos(db, fab):
    from src.db import usuario as U
    u = fab.usuario(nombre="LOCK_TEST_1", password="Clave_Correcta_123")
    for _ in range(5):
        assert U.validar_login_usuario("LOCK_TEST_1", "incorrecta") is None
    intentos, bloqueado_hasta = _campos(db, u["id"])
    assert intentos >= 5 and bloqueado_hasta is not None
    # Aún con la contraseña correcta, está bloqueado temporalmente.
    assert U.validar_login_usuario("LOCK_TEST_1", "Clave_Correcta_123") is None


def test_exito_resetea_contador(db, fab):
    from src.db import usuario as U
    u = fab.usuario(nombre="RESET_TEST_1", password="Clave_Correcta_123")
    assert U.validar_login_usuario("RESET_TEST_1", "incorrecta") is None
    assert _campos(db, u["id"])[0] == 1
    assert U.validar_login_usuario("RESET_TEST_1", "Clave_Correcta_123") is not None
    intentos, bloqueado = _campos(db, u["id"])
    assert intentos == 0 and bloqueado is None
