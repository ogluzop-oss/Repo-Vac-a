"""
Tests · Dispositivos de confianza MFA (Fase 4). Verifica registrar/validar/revocar/caducar y el
aislamiento estricto por (usuario + empresa + terminal). Capa de confianza sobre `ioc_terminales`;
no crea sistema de dispositivos paralelo.
"""

import pytest

pytestmark = pytest.mark.db

UID = "777010"
UID2 = "777011"
T1 = "TPV-A"
T2 = "PDA-B"
E1 = "E1"
E2 = "E2"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM mfa_dispositivos_confianza WHERE id_usuario IN (%s,%s)", (UID, UID2))
            c.commit()
    _b()
    yield
    _b()


def test_registrar_y_validar(limpia):
    from src.services.seguridad import mfa_dispositivos as D
    assert D.registrar_confianza(UID, T1, E1)["ok"] is True
    assert D.es_de_confianza(UID, T1, E1) is True


def test_aislamiento_usuario_empresa_terminal(limpia):
    from src.services.seguridad import mfa_dispositivos as D
    D.registrar_confianza(UID, T1, E1)
    assert D.es_de_confianza(UID, T2, E1) is False    # otro terminal
    assert D.es_de_confianza(UID, T1, E2) is False    # otra empresa
    assert D.es_de_confianza(UID2, T1, E1) is False   # otro usuario
    assert D.es_de_confianza(UID, "", E1) is False     # sin terminal → nunca confía


def test_revocar_y_caducar(limpia):
    from src.services.seguridad import mfa_dispositivos as D
    D.registrar_confianza(UID, T1, E1)
    devs = D.listar(id_usuario=UID)
    assert len(devs) == 1
    assert D.revocar(devs[0]["id"])["ok"] is True
    assert D.es_de_confianza(UID, T1, E1) is False    # revocado
    # Ventana de confianza caducada → no confía.
    D.registrar_confianza(UID, T2, E1, dias=-1)
    assert D.es_de_confianza(UID, T2, E1) is False
