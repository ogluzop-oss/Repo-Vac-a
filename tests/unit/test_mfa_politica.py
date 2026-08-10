"""
Tests · Gobernanza MFA (Fase 0): permisos RBAC, política MFA por empresa (patrón password_politica),
política efectiva por USUARIO+EMPRESA+ROL y saneado de secretos en los eventos MFA. Sin motores nuevos.
"""

import pytest

pytestmark = pytest.mark.db

EMP_A = "T-MFA-A"
EMP_B = "T-MFA-B"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM mfa_politica WHERE id_empresa IN (%s,%s)", (EMP_A, EMP_B))
            conn.commit()
    _b()
    yield
    _b()


def test_rbac_catalogo_mfa():
    from src.services.seguridad import catalogo as C
    seis = {"mfa.self.manage", "mfa.admin.enforce", "mfa.admin.reset", "mfa.admin.disable",
            "mfa.devices.manage", "mfa.events.view"}
    assert seis <= set(C.CATALOGO)
    # El factor propio lo gestionan todos los roles; enforce/disable quedan para admin (comodín).
    assert "mfa.self.manage" in C.ROLES_SISTEMA["OPERARIO"]["permisos"]
    assert {"mfa.self.manage", "mfa.admin.reset", "mfa.devices.manage", "mfa.events.view"} <= set(
        C.ROLES_SISTEMA["GERENTE"]["permisos"])
    assert C.ROLES_SISTEMA["ADMINISTRADOR"]["permisos"] == "*"


def test_politica_defecto_opcional(limpia):
    from src.services.seguridad import mfa_politica as P
    pol = P.obtener_politica(EMP_A)
    assert pol["modo"] == "opcional" and pol["metodos"] == "totp"


def test_politica_efectiva_por_empresa_y_rol(limpia):
    from src.services.seguridad import mfa_politica as P
    # Empresa A: MFA obligatorio para todos.
    assert P.guardar_politica(EMP_A, modo="obligatorio", metodos="totp,webauthn")["ok"]
    # Empresa B: opcional, pero obligatorio por override para ADMINISTRADOR.
    assert P.guardar_politica(EMP_B, modo="opcional", roles_obligatorios="administrador")["ok"]
    assert P.politica_efectiva({"perfil": "OPERARIO"}, id_empresa=EMP_A)["obligatorio"] is True
    assert P.politica_efectiva({"perfil": "OPERARIO"}, id_empresa=EMP_B)["obligatorio"] is False
    assert P.politica_efectiva({"perfil": "ADMINISTRADOR"}, id_empresa=EMP_B)["obligatorio"] is True
    # Métodos normalizados a la lista canónica.
    assert set(P.politica_efectiva({"perfil": "X"}, id_empresa=EMP_A)["metodos"]) == {"totp", "webauthn"}
    # Aislamiento: A y B no comparten política.
    assert P.obtener_politica(EMP_A)["modo"] != P.obtener_politica(EMP_B)["modo"]


def test_politica_desactivada(limpia):
    from src.services.seguridad import mfa_politica as P
    P.guardar_politica(EMP_A, modo="obligatorio", activo=0)
    ef = P.politica_efectiva({"perfil": "ADMINISTRADOR"}, id_empresa=EMP_A)
    assert ef["modo"] == "desactivado" and ef["obligatorio"] is False


def test_eventos_taxonomia_y_saneo():
    from src.services.seguridad import mfa_eventos as E
    assert {"MFA_ENROLLMENT_STARTED", "MFA_ENROLLED", "MFA_SUCCESS", "MFA_FAILURE", "MFA_RESET",
            "MFA_RECOVERY_USED", "TRUSTED_DEVICE_ADDED", "MFA_POLICY_CHANGED"} <= set(E.EVENTOS)
    # NUNCA se filtran secretos: el valor sensible se enmascara.
    san = E._sanea("intento secreto=ABC123 recovery=999 token=xyz")
    assert "ABC123" not in san and "999" not in san and "xyz" not in san and "***" in san
    E.emitir("MFA_SUCCESS", id_usuario=1, id_empresa=EMP_A, detalle="ok")  # no lanza
