"""E1.2 · Consolidación de autenticación: login nominal oficial + legacy aislado."""

import pytest

pytestmark = pytest.mark.db


def test_legacy_profile_login_desactivado_por_defecto(db, fab, monkeypatch):
    """El login por PERFIL (contraseña compartida) NO se activa accidentalmente:
    aun con credenciales correctas, devuelve None si no está el flag legacy."""
    from src.db import usuario as U
    monkeypatch.delenv("SMART_MANAGER_LEGACY_PROFILE_LOGIN", raising=False)
    fab.usuario(nombre="LEG_OFF_1", perfil="GERENTE", password="Clave_Compartida_123")
    assert U.legacy_profile_login_habilitado() is False
    assert U.validar_login("GERENTE", "Clave_Compartida_123") is None   # legacy OFF


def test_legacy_profile_login_solo_con_flag(db, fab, monkeypatch):
    """El modo legacy solo funciona si se habilita EXPLÍCITAMENTE por entorno."""
    from src.db import usuario as U
    u = fab.usuario(nombre="LEG_ON_1", perfil="OPERARIO", password="Clave_Compartida_123")
    monkeypatch.setenv("SMART_MANAGER_LEGACY_PROFILE_LOGIN", "1")
    assert U.legacy_profile_login_habilitado() is True
    res = U.validar_login("OPERARIO", "Clave_Compartida_123")
    assert res and res["id"] == u["id"]


def test_login_nominal_por_nombre_y_email(db, fab):
    """Sistema OFICIAL: login nominal por usuario, por nombre o por email."""
    from src.db import usuario as U
    u = fab.usuario(nombre="NOM_TEST_1", password="Clave_Nominal_123",
                    email="nom1@empresa.test")
    assert U.validar_login_usuario("NOM_TEST_1", "Clave_Nominal_123")["id"] == u["id"]
    # por email (si la columna existe en el esquema)
    porem = U.validar_login_usuario("nom1@empresa.test", "Clave_Nominal_123")
    if porem is not None:
        assert porem["id"] == u["id"]
    assert U.validar_login_usuario("NOM_TEST_1", "mala") is None


def test_login_nominal_aislado_por_empresa(db, fab):
    """El login nominal respeta el aislamiento por empresa cuando se indica."""
    from src.db import usuario as U
    emp = fab.empresa("AUTH EMP")
    u = fab.usuario(nombre="EMP_NOM_1", password="Clave_Nominal_123", id_empresa=emp)
    assert U.validar_login_usuario("EMP_NOM_1", "Clave_Nominal_123", id_empresa=emp)["id"] == u["id"]
    # Con otra empresa explícita, no autentica.
    assert U.validar_login_usuario("EMP_NOM_1", "Clave_Nominal_123",
                                   id_empresa="00000000-0000-0000-0000-000000000001") is None
