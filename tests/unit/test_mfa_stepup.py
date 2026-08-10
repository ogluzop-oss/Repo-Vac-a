"""
Tests · Step-Up Authentication (Fase 7). Verifica el registro de acciones críticas, la ventana temporal
de confianza (abre/expira/aísla por usuario+empresa/invalida) y la verificación del 2º factor (TOTP y
recovery). Reutiliza el motor `seguridad.mfa`; la ventana es efímera (no persiste).
"""

import pytest

pytestmark = pytest.mark.db

UID = 755010
EMP = "E1"


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


def test_acciones_criticas_registro():
    from src.services.seguridad import mfa_stepup as SU
    for a in ("password.cambiar", "email.cambiar", "mfa.desactivar", "mfa.recovery.regenerar",
              "mfa.admin.reset", "roles.cambiar", "permisos.cambiar", "pagos.pasarela.configurar",
              "canal_web.dominios", "secretos.acceder", "saas.admin", "finanzas.critica"):
        assert SU.requiere(a) is True
    assert SU.requiere("ventas.ver") is False


def test_ventana_temporal(limpia):
    from src.services.seguridad import mfa_stepup as SU
    assert SU.reciente(UID, id_empresa=EMP) is False
    SU.registrar(UID, id_empresa=EMP, accion="roles.cambiar")
    assert SU.reciente(UID, id_empresa=EMP) is True
    assert SU.reciente(UID, id_empresa=EMP, ventana_seg=0) is False   # caducada
    assert SU.reciente(UID, id_empresa="OTRA") is False               # aislamiento por empresa
    SU.invalidar(UID, id_empresa=EMP)
    assert SU.reciente(UID, id_empresa=EMP) is False


def test_verificar_totp_y_recovery(limpia):
    from src.services.seguridad import mfa, mfa_stepup as SU
    rr = mfa.iniciar_activacion(UID, "t")
    r = mfa.confirmar_activacion(UID, mfa.codigo_actual(rr["secreto"]))
    rec = r.get("recovery_codes") or []
    # TOTP válido → step-up ok y abre ventana.
    assert SU.verificar(UID, mfa.codigo_actual(mfa._secreto(UID)), id_empresa=EMP,
                        accion="mfa.recovery.regenerar") is True
    assert SU.reciente(UID, id_empresa=EMP) is True
    SU.invalidar(UID, id_empresa=EMP)
    # Recovery code para step-up: SOLO si la política lo permite (Fase 10 · gating).
    from src.services.seguridad import mfa_politica
    mfa_politica.guardar_politica(EMP, modo="opcional", metodos="totp,recovery")
    assert SU.verificar(UID, rec[0], id_empresa=EMP, accion="mfa.desactivar") is True
    # Código inválido → falla.
    assert SU.verificar(UID, "000000", id_empresa=EMP) is False
    mfa.desactivar(UID)
