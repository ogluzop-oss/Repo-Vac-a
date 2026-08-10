"""
Tests · MFA en la API humana (Fase 2). Verifica que `/auth/login` NO emite un JWT completo si el
usuario tiene 2º factor activo (cierra el bypass), que el `mfa_token` temporal no sirve como access, y
que `/auth/mfa` emite el JWT completo (amr ["pwd","otp"], mfa=True) solo con un 2º factor válido.
Las credenciales se simulan con monkeypatch; el motor MFA (`seguridad.mfa`) es el real.
"""

import pytest

pytestmark = pytest.mark.db

UID = 999201
USER = {"id": UID, "nombre": "t", "id_empresa": None, "perfil": "OPERARIO", "tienda_id": None}


@pytest.fixture()
def client(monkeypatch, db):
    from flask import Blueprint, Flask
    from src.api.routers import auth
    monkeypatch.setattr("src.db.usuario.validar_login_usuario",
                        lambda usuario, password, id_empresa=None: (USER if password == "good" else None))
    app = Flask(__name__)
    bp = Blueprint("api", __name__)
    auth.registrar(bp)
    app.register_blueprint(bp)

    def _clean():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM mfa_usuarios WHERE id_usuario=%s", (UID,))
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (UID,))
            c.commit()
    _clean()
    yield app.test_client()
    _clean()


def test_login_sin_mfa_emite_jwt(client):
    from src.seguridad import tokens
    r = client.post("/auth/login", json={"usuario": "t", "password": "good"}).get_json()
    assert "access" in r
    assert tokens.verificar(r["access"], "access")["amr"] == ["pwd"]
    # Credenciales inválidas → 401.
    assert client.post("/auth/login", json={"usuario": "t", "password": "bad"}).status_code == 401


def test_login_con_mfa_exige_segundo_factor(client):
    from src.seguridad import tokens
    from src.services.seguridad import mfa
    rr = mfa.iniciar_activacion(UID, "t")
    mfa.confirmar_activacion(UID, mfa.codigo_actual(rr["secreto"]))

    r = client.post("/auth/login", json={"usuario": "t", "password": "good"}).get_json()
    assert r.get("mfa_required") is True and "access" not in r and r.get("mfa_token")
    mtok = r["mfa_token"]
    # El token PENDING no sirve como access → los endpoints protegidos lo rechazan (sin bypass).
    assert tokens.verificar(mtok, "access") is None
    assert tokens.verificar(mtok, "mfa_pending") is not None

    # Segundo factor válido → JWT completo con amr ["pwd","otp"] y mfa=True.
    cod = mfa.codigo_actual(mfa._secreto(UID))
    resp = client.post("/auth/mfa", json={"mfa_token": mtok, "codigo": cod})
    assert resp.status_code == 200
    cl = tokens.verificar(resp.get_json()["access"], "access")
    assert cl["amr"] == ["pwd", "otp"] and cl["mfa"] is True

    # Código inválido o token inválido → 401.
    assert client.post("/auth/mfa", json={"mfa_token": mtok, "codigo": "000000"}).status_code == 401
    assert client.post("/auth/mfa", json={"mfa_token": "xxx", "codigo": cod}).status_code == 401
    mfa.desactivar(UID)


def test_token_mfa_pending_no_es_access():
    from src.seguridad import tokens
    tok = tokens.emitir_mfa_pending(USER)
    assert tokens.verificar(tok, "access") is None            # nunca vale como access
    assert tokens.verificar(tok, "mfa_pending")["mfa"] is False
