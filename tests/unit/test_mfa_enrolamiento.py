"""
Tests · Enrolamiento MFA (Fase 1). Verifica el flujo de autoservicio de `gui/mfa_gui`: iniciar
activación (secreto+URI otpauth), confirmar con un TOTP válido → MFA activo + recovery codes hasheados,
y que el panel refleja el estado. Reutiliza el motor `seguridad.mfa` (no lo modifica).
"""

import pytest

pytestmark = pytest.mark.db

UID = 999124


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


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


def test_enrolamiento_activa_y_genera_recovery(qapp, db, limpia):
    from src.services.seguridad import mfa
    from src.gui.mfa_gui import MFAEnrolamientoDialog, MFASeguridadPanel

    usuario = {"id": UID, "nombre": "mfa_test", "perfil": "OPERARIO", "id_empresa": None}
    dlg = MFAEnrolamientoDialog(usuario)
    assert (dlg._uri or "").startswith("otpauth://") and len(dlg._secreto or "") >= 16
    # Confirmar con un código TOTP válido calculado del secreto → activa MFA.
    dlg._code.setText(mfa.codigo_actual(dlg._secreto))
    dlg._activar()
    assert dlg.activado is True
    assert mfa.mfa_activo(UID) is True
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM mfa_recovery_codes WHERE id_usuario=%s", (UID,))
        assert cur.fetchone()[0] == 8   # recovery codes generados (hasheados por el motor)

    panel = MFASeguridadPanel(usuario=usuario)
    assert "ACTIVO" in panel.lbl_estado.text()
    mfa.desactivar(UID)


def test_codigo_invalido_no_activa(qapp, db, limpia):
    from src.services.seguridad import mfa
    from src.gui.mfa_gui import MFAEnrolamientoDialog

    dlg = MFAEnrolamientoDialog({"id": UID, "nombre": "mfa_test", "perfil": "OPERARIO"})
    dlg._code.setText("000000")   # código casi seguro inválido
    dlg._activar()
    assert dlg.activado is False
    assert mfa.mfa_activo(UID) is False
