"""
Tests · Cierre y consolidación MFA. Verifica: claim `auth_time` + `mfa_reciente`, el guard API
`requiere_step_up` (M2M pasa; humano reciente pasa; humano sin/viejo MFA → 401), `/auth/step-up`
(refresca recencia), y el gating de recovery codes para step-up según la política. Reutiliza el motor
MFA existente; ningún sistema paralelo.
"""

import time

import pytest

pytestmark = pytest.mark.db

UID = 744010
EMP = "SUC1"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM mfa_usuarios WHERE id_usuario=%s", (UID,))
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (UID,))
            cur.execute("DELETE FROM mfa_politica WHERE id_empresa=%s", (EMP,))
            c.commit()
        from src.services.seguridad import mfa_stepup
        mfa_stepup.invalidar(UID, id_empresa=EMP)
    _b()
    yield
    _b()


def test_auth_time_y_reciente():
    from src.seguridad import tokens
    fresco = tokens.emitir_access({"id": 1, "id_empresa": "E"}, amr=["pwd", "otp"],
                                  auth_time=int(time.time()))
    assert tokens.mfa_reciente(tokens.verificar(fresco, "access")) is True
    viejo = tokens.emitir_access({"id": 1, "id_empresa": "E"}, amr=["pwd", "otp"],
                                 auth_time=int(time.time()) - 9999)
    assert tokens.mfa_reciente(tokens.verificar(viejo, "access")) is False
    pwd = tokens.emitir_access({"id": 1, "id_empresa": "E"}, amr=["pwd"], auth_time=int(time.time()))
    assert tokens.mfa_reciente(tokens.verificar(pwd, "access")) is False


def test_guard_requiere_step_up(monkeypatch):
    from flask import Flask, jsonify
    from src.api.security import requiere_step_up
    from src.seguridad import tokens
    app = Flask(__name__)

    @app.post("/sensible")
    @requiere_step_up("finanzas.critica")
    def _s():
        return jsonify({"ok": True})

    cli = app.test_client()
    fresco = tokens.emitir_access({"id": 1, "id_empresa": "E", "perfil": "GERENTE"},
                                  amr=["pwd", "otp"], auth_time=int(time.time()))
    assert cli.post("/sensible", headers={"Authorization": f"Bearer {fresco}"}).status_code == 200
    viejo = tokens.emitir_access({"id": 1, "id_empresa": "E"}, amr=["pwd", "otp"],
                                 auth_time=int(time.time()) - 9999)
    r = cli.post("/sensible", headers={"Authorization": f"Bearer {viejo}"})
    assert r.status_code == 401 and r.get_json()["error"] == "step_up_required"
    pwd = tokens.emitir_access({"id": 1, "id_empresa": "E"}, amr=["pwd"], auth_time=int(time.time()))
    r = cli.post("/sensible", headers={"Authorization": f"Bearer {pwd}"})
    assert r.status_code == 401 and r.get_json()["error"] == "mfa_enrollment_required"
    # API key / M2M → sin MFA humano.
    monkeypatch.setenv("API_MASTER_KEY", "K")
    assert cli.post("/sensible", headers={"X-API-Key": "K", "X-Empresa-Id": "E"}).status_code == 200


def test_auth_step_up_refresca_recencia(limpia):
    from flask import Blueprint, Flask
    from src.api.routers import auth
    from src.seguridad import tokens
    from src.services.seguridad import mfa
    rr = mfa.iniciar_activacion(UID, "t")
    mfa.confirmar_activacion(UID, mfa.codigo_actual(rr["secreto"]))
    app = Flask(__name__)
    bp = Blueprint("api", __name__)
    auth.registrar(bp)
    app.register_blueprint(bp)
    cli = app.test_client()
    # Token humano SIN recencia (pwd-only) → step-up con TOTP → access nuevo reciente.
    acc = tokens.emitir_access({"id": UID, "id_empresa": EMP, "perfil": "GERENTE", "nombre": "g"},
                               amr=["pwd"], auth_time=int(time.time()) - 9999)
    r = cli.post("/auth/step-up", headers={"Authorization": f"Bearer {acc}"},
                 json={"codigo": mfa.codigo_actual(mfa._secreto(UID)), "accion": "finanzas.critica"})
    assert r.status_code == 200
    nuevo = tokens.verificar(r.get_json()["access"], "access")
    assert tokens.mfa_reciente(nuevo) is True and nuevo["amr"] == ["pwd", "otp"]
    # Código inválido → 401.
    assert cli.post("/auth/step-up", headers={"Authorization": f"Bearer {acc}"},
                    json={"codigo": "000000"}).status_code == 401
    mfa.desactivar(UID)


def test_recovery_gating_stepup(limpia):
    from src.services.seguridad import mfa, mfa_politica, mfa_stepup
    rr = mfa.iniciar_activacion(UID, "t")
    rc = mfa.confirmar_activacion(UID, mfa.codigo_actual(rr["secreto"]))
    rec = rc["recovery_codes"]
    # Política SIN recovery → un recovery code NO sirve para step-up de alto riesgo.
    mfa_politica.guardar_politica(EMP, modo="obligatorio", metodos="totp")
    assert mfa_stepup.verificar(UID, rec[0], id_empresa=EMP, accion="finanzas.critica") is False
    # Política CON recovery → sí se permite.
    mfa_politica.guardar_politica(EMP, modo="obligatorio", metodos="totp,recovery")
    assert mfa_stepup.verificar(UID, rec[0], id_empresa=EMP, accion="finanzas.critica") is True
    mfa.desactivar(UID)
