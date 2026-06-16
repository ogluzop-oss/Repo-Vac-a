"""Integración · A5.2/A5.3: rate limiting + no-exposición de secretos en la API."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db):
    from src.backend.app import crear_app
    return crear_app().test_client()


def test_rate_limit_login_429(db, cliente):
    from src.seguridad import rate_limit as RL
    RL.backend().reset()
    # El límite de login es 10/min; el 11º intento debe devolver 429.
    codigos = [cliente.post("/api/v1/auth/login",
                            json={"usuario": "x", "password": "y"}).status_code
               for _ in range(11)]
    assert codigos[-1] == 429 and codigos.count(429) >= 1
    assert all(c in (401, 400) for c in codigos[:10])   # los 10 primeros, no limitados


def test_login_no_expone_password_ni_hash(db, fab, cliente):
    from src.seguridad import rate_limit as RL
    RL.backend().reset()
    u = fab.usuario(nombre="SEC_USER_1", password="Clave_Sec_123456")
    fab.al_limpiar(lambda: _borra_sesiones(db, u["id"]))
    r = cliente.post("/api/v1/auth/login",
                     json={"usuario": "SEC_USER_1", "password": "Clave_Sec_123456"})
    j = r.get_json()
    # login devuelve tokens (a proposito) pero NUNCA password/hash del usuario.
    blob = str(j).lower()
    assert "Clave_Sec_123456".lower() not in blob
    assert "password" not in j.get("usuario", {}) and "hash" not in str(j.get("usuario", {})).lower()


def test_recursos_no_exponen_secretos(db, fab, cliente):
    from src.seguridad import rate_limit as RL
    RL.backend().reset()
    fab.usuario(nombre="SEC_USER_2", password="Clave_Sec_123456", perfil="ADMINISTRADOR")
    tok = cliente.post("/api/v1/auth/login",
                       json={"usuario": "SEC_USER_2", "password": "Clave_Sec_123456"}).get_json()["access"]
    h = {"Authorization": f"Bearer {tok}"}
    prohibidas = ("password", "api_key", "api_secret", "webhook_secret", "secret",
                  "token", "refresh_hash", "clave")

    def _claves(obj, acc):
        if isinstance(obj, dict):
            for k, v in obj.items():
                acc.add(str(k).lower()); _claves(v, acc)
        elif isinstance(obj, list):
            for x in obj:
                _claves(x, acc)
        return acc

    for ruta in ("/api/v1/catalogo/productos", "/api/v1/catalogo/categorias", "/api/v1/pedidos"):
        j = cliente.get(ruta, headers=h).get_json()
        claves = _claves(j, set())
        fugas = {k for k in claves if any(s in k for s in prohibidas)}
        assert not fugas, f"{ruta} expone claves sensibles: {fugas}"


def _borra_sesiones(db, uid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM sesiones WHERE id_usuario=%s", (uid,))
        conn.commit()
