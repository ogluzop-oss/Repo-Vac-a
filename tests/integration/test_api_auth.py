"""Integración · API REST A1.1: auth JWT, middleware de tenant, CORS, versión."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db):
    from src.backend.app import crear_app
    return crear_app().test_client()


def _usuario(db, fab, password="Clave_Api_123456", **kw):
    u = fab.usuario(password=password, **kw)
    fab.al_limpiar(lambda: _borra_sesiones(db, u["id"]))
    return u


def test_info_version_publica(cliente):
    r = cliente.get("/api/v1/")
    assert r.status_code == 200 and r.get_json()["version"] == "v1"


def test_login_ok_y_credenciales_invalidas(db, fab, cliente):
    u = _usuario(db, fab, nombre="API_USER_1", perfil="GERENTE")
    r = cliente.post("/api/v1/auth/login",
                     json={"usuario": "API_USER_1", "password": "Clave_Api_123456"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["access"] and j["refresh"] and j["usuario"]["id"] == u["id"]
    assert j["usuario"]["rol"] == "GERENTE"
    # Contraseña incorrecta.
    assert cliente.post("/api/v1/auth/login",
                        json={"usuario": "API_USER_1", "password": "mala"}).status_code == 401


def test_me_requiere_token(db, fab, cliente):
    _usuario(db, fab, nombre="API_USER_2")
    assert cliente.get("/api/v1/auth/me").status_code == 401
    tok = cliente.post("/api/v1/auth/login",
                       json={"usuario": "API_USER_2", "password": "Clave_Api_123456"}).get_json()["access"]
    r = cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.get_json()["usuario"]["nombre"] is not None


def test_refresh_emite_nuevo_access(db, fab, cliente):
    _usuario(db, fab, nombre="API_USER_3")
    log = cliente.post("/api/v1/auth/login",
                       json={"usuario": "API_USER_3", "password": "Clave_Api_123456"}).get_json()
    r = cliente.post("/api/v1/auth/refresh", json={"refresh": log["refresh"]})
    assert r.status_code == 200 and r.get_json()["access"]
    # El nuevo access funciona.
    nuevo = r.get_json()["access"]
    assert cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {nuevo}"}).status_code == 200


def test_logout_revoca_refresh(db, fab, cliente):
    _usuario(db, fab, nombre="API_USER_4")
    log = cliente.post("/api/v1/auth/login",
                       json={"usuario": "API_USER_4", "password": "Clave_Api_123456"}).get_json()
    assert cliente.post("/api/v1/auth/logout", json={"refresh": log["refresh"]}).status_code == 200
    # Tras logout, el refresh ya no sirve.
    assert cliente.post("/api/v1/auth/refresh", json={"refresh": log["refresh"]}).status_code == 401


def test_tenant_context_desde_token(db, fab, cliente):
    emp_b = fab.empresa("EMP API B")
    _usuario(db, fab, nombre="API_USER_B", id_empresa=emp_b)
    tok = cliente.post("/api/v1/auth/login",
                       json={"usuario": "API_USER_B", "password": "Clave_Api_123456",
                             "empresa": emp_b}).get_json()["access"]
    r = cliente.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.get_json()["usuario"]["empresa"] == emp_b


def test_cors_lista_blanca(db, fab, cliente, monkeypatch):
    monkeypatch.setenv("API_CORS_ORIGINS", "https://app.test, https://otra.test")
    # Origen permitido → cabecera ACAO con ese origen.
    r = cliente.get("/api/v1/", headers={"Origin": "https://app.test"})
    assert r.headers.get("Access-Control-Allow-Origin") == "https://app.test"
    # Origen NO permitido → sin ACAO (nunca '*').
    r2 = cliente.get("/api/v1/", headers={"Origin": "https://malicioso.test"})
    assert r2.headers.get("Access-Control-Allow-Origin") is None
    # Preflight responde 204.
    assert cliente.options("/api/v1/auth/login").status_code == 204


def _borra_sesiones(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM sesiones WHERE id_usuario=%s", (uid,))
        conn.commit()
