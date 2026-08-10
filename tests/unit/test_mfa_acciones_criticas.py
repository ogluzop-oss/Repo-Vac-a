"""
Tests · Cableado de acciones críticas de negocio al Step-Up MFA (fase final). Verifica que las 8
acciones críticas están registradas, que el atajo de escritorio `step_up_sesion` toma el usuario de la
sesión activa y delega en el guard oficial `pedir_step_up` (RBAC primero, luego step-up), que es
degradable (no bloquea si no hay sesión / MFA inactivo) y que respeta el aislamiento usuario+empresa.
No crea motores ni endpoints nuevos: reutiliza `gui.mfa_gui` + `services.seguridad.mfa_stepup`.
"""

import pytest

pytestmark = pytest.mark.db

# Las 8 acciones críticas de negocio cableadas en esta fase (+ las 4 ya cableadas del MFA propio).
ACCIONES_NEGOCIO = ("email.cambiar", "roles.cambiar", "permisos.cambiar",
                    "pagos.pasarela.configurar", "canal_web.dominios", "secretos.acceder",
                    "saas.admin", "finanzas.critica")


def test_acciones_negocio_registradas():
    from src.services.seguridad import mfa_stepup as SU
    for a in ACCIONES_NEGOCIO:
        assert SU.requiere(a) is True, a
    # Una acción no crítica NO exige step-up.
    assert SU.requiere("ventas.ver") is False


def test_step_up_sesion_delega_usuario_de_sesion(monkeypatch):
    """`step_up_sesion(accion)` debe llamar a `pedir_step_up` con el usuario de `sesion_global`."""
    from src.gui import mfa_gui
    capturado = {}

    def _fake(usuario, accion, parent=None):
        capturado["usuario"] = usuario
        capturado["accion"] = accion
        return True

    monkeypatch.setattr(mfa_gui, "pedir_step_up", _fake)
    from src.db.usuario import sesion_global
    sesion_global.usuario_actual = {"id": 4242, "id_empresa": "EMP_X", "perfil": "ADMINISTRADOR"}
    try:
        assert mfa_gui.step_up_sesion("roles.cambiar") is True
        assert capturado["accion"] == "roles.cambiar"
        assert capturado["usuario"]["id"] == 4242
        assert capturado["usuario"]["id_empresa"] == "EMP_X"
    finally:
        sesion_global.usuario_actual = None


def test_step_up_sesion_sin_mfa_activo_pasa():
    """Sin MFA activo (ni sesión), el guard NO bloquea: el control queda en RBAC/reauth del llamador."""
    from src.gui import mfa_gui
    from src.db.usuario import sesion_global
    sesion_global.usuario_actual = None
    # Usuario inexistente => sin MFA activo => pedir_step_up devuelve True (degradable, no bloquea).
    assert mfa_gui.step_up_sesion("finanzas.critica") is True


def test_step_up_sesion_degradable_ante_error(monkeypatch):
    """Si el subsistema MFA lanza, `step_up_sesion` no bloquea el flujo legítimo (devuelve True)."""
    from src.gui import mfa_gui

    def _boom(*a, **k):
        raise RuntimeError("mfa caido")

    monkeypatch.setattr(mfa_gui, "pedir_step_up", _boom)
    assert mfa_gui.step_up_sesion("pagos.pasarela.configurar") is True
