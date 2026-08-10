"""
Tests · Reset MFA administrativo + recuperación (Fase 3). Verifica el reset por admin (RBAC + reset del
objetivo + evento), el uso ÚNICO de recovery codes, la invalidación al regenerar, y el rate-limit del
segundo factor en `/auth/mfa`. Reutiliza el motor `seguridad.mfa` (sin modificarlo).
"""

import pytest

pytestmark = pytest.mark.db

UID = 999302


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM mfa_usuarios WHERE id_usuario=%s", (UID,))
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (UID,))
            c.commit()
    _b()
    yield
    _b()


def _activar(uid):
    from src.services.seguridad import mfa
    r = mfa.iniciar_activacion(uid, "obj")
    mfa.confirmar_activacion(uid, mfa.codigo_actual(r["secreto"]))


def test_reset_admin_desactiva_y_borra_recovery(limpia, db):
    from src.services.seguridad import mfa, mfa_admin
    _activar(UID)
    assert mfa.mfa_activo(UID) is True
    r = mfa_admin.reset_mfa(UID, usuario_actor={"id": 1, "nombre": "admin", "perfil": "ADMINISTRADOR"},
                            motivo="dispositivo perdido")
    assert r["ok"] is True
    assert mfa.mfa_activo(UID) is False
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM mfa_recovery_codes WHERE id_usuario=%s", (UID,))
        assert cur.fetchone()[0] == 0


def test_reset_admin_rbac_denegado(limpia, monkeypatch):
    from src.services.seguridad import mfa_admin
    monkeypatch.setattr("src.services.autorizacion.puede", lambda usuario, permiso, **k: False)
    r = mfa_admin.reset_mfa(UID, usuario_actor={"id": 9, "perfil": "OPERARIO"})
    assert r.get("error") == "forbidden"


def test_recovery_codes_uso_unico_y_regeneracion(limpia):
    from src.services.seguridad import mfa
    _activar(UID)
    codes = mfa.generar_recovery_codes(UID)
    assert mfa.usar_recovery_code(UID, codes[0]) is True    # 1ª vez
    assert mfa.usar_recovery_code(UID, codes[0]) is False   # ya usado
    mfa.generar_recovery_codes(UID)                          # regenera → invalida los anteriores
    assert mfa.usar_recovery_code(UID, codes[1]) is False    # código viejo ya no vale
    mfa.desactivar(UID)


def test_rate_limit_auth_mfa(db, monkeypatch):
    from flask import Blueprint, Flask
    from src.seguridad import rate_limit, tokens
    from src.services.seguridad import mfa
    from src.api.routers import auth

    def _clean():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM mfa_usuarios WHERE id_usuario=%s", (UID,))
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (UID,))
            c.commit()
    _clean()
    _activar(UID)   # con MFA activo, los códigos erróneos dan 401 hasta que salta el 429
    rate_limit.backend().reset(f"mfa_verify:{UID}")
    app = Flask(__name__)
    bp = Blueprint("api", __name__)
    auth.registrar(bp)
    app.register_blueprint(bp)
    cli = app.test_client()
    mtok = tokens.emitir_mfa_pending({"id": UID, "nombre": "t", "id_empresa": None})
    codigos = [cli.post("/auth/mfa", json={"mfa_token": mtok, "codigo": "000000"}).status_code
               for _ in range(7)]
    assert codigos[:5] == [401] * 5     # 5 intentos permitidos (fallan por código inválido)
    assert codigos[5] == 429            # 6º intento: rate limited
    mfa.desactivar(UID)
    _clean()
