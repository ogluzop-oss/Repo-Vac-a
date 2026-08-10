"""
Tests · MFA adaptativo (Fase 6). Matriz de casos que verifica el orden POLÍTICA EMPRESA → OVERRIDE ROL
→ CONTEXTO, el suelo de roles críticos, y la decisión combinada (`mfa_decision.evaluar`) con factor
activo y dispositivo de confianza. Sin motor nuevo (orquesta política + factor + confianza).
"""

import pytest

pytestmark = pytest.mark.db

E1 = "TAF1"   # empresa opcional
E2 = "TAF2"   # empresa obligatoria
UID = 766010


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM mfa_politica WHERE id_empresa IN (%s,%s)", (E1, E2))
            cur.execute("DELETE FROM mfa_usuarios WHERE id_usuario=%s", (UID,))
            cur.execute("DELETE FROM mfa_recovery_codes WHERE id_usuario=%s", (UID,))
            cur.execute("DELETE FROM mfa_dispositivos_confianza WHERE id_usuario=%s", (str(UID),))
            c.commit()
    _b()
    yield
    _b()


def test_politica_adaptativa_matriz(limpia):
    from src.services.seguridad import mfa_politica as P
    P.guardar_politica(E1, modo="opcional")
    P.guardar_politica(E2, modo="obligatorio")
    # Suelo crítico: ADMIN/SUPERADMIN siempre obligatorio (aunque la empresa sea opcional).
    assert P.politica_efectiva({"perfil": "ADMINISTRADOR"}, id_empresa=E1)["obligatorio"] is True
    assert P.politica_efectiva({"perfil": "SUPERADMIN"}, id_empresa=E1)["obligatorio"] is True
    # Usuario de oficina: según la empresa.
    assert P.politica_efectiva({"perfil": "OPERARIO"}, id_empresa=E1)["obligatorio"] is False
    assert P.politica_efectiva({"perfil": "OPERARIO"}, id_empresa=E2)["obligatorio"] is True
    # Contexto NO humano / autoservicio: nunca obligatorio interactivo.
    assert P.politica_efectiva({"perfil": "ADMINISTRADOR"}, id_empresa=E1, contexto="api")["obligatorio"] is False
    assert P.politica_efectiva({"perfil": "OPERARIO"}, id_empresa=E1, contexto="autocobro")["obligatorio"] is False
    # Override por rol (empresa opcional que obliga a GERENTE).
    P.guardar_politica(E1, modo="opcional", roles_obligatorios="GERENTE")
    assert P.politica_efectiva({"perfil": "GERENTE"}, id_empresa=E1)["obligatorio"] is True
    assert P.politica_efectiva({"perfil": "OPERARIO"}, id_empresa=E1)["obligatorio"] is False


def test_decision_combinada(limpia):
    from src.services.seguridad import mfa, mfa_dispositivos, mfa_decision as DEC
    from src.services.seguridad import mfa_politica as P
    P.guardar_politica(E1, modo="opcional")
    # ADMIN sin MFA: obligatorio (suelo) pero no hay factor → debe_enrolar, sin reto.
    d = DEC.evaluar({"id": UID, "perfil": "ADMINISTRADOR"}, id_empresa=E1)
    assert d["obligatorio"] is True and d["debe_enrolar"] is True and d["reto_requerido"] is False
    # OPERARIO sin MFA: nada.
    d = DEC.evaluar({"id": UID, "perfil": "OPERARIO"}, id_empresa=E1)
    assert d["reto_requerido"] is False and d["debe_enrolar"] is False
    # Con MFA activo y sin terminal → reto.
    rr = mfa.iniciar_activacion(UID, "t")
    mfa.confirmar_activacion(UID, mfa.codigo_actual(rr["secreto"]))
    assert DEC.evaluar({"id": UID, "perfil": "OPERARIO"}, id_empresa=E1)["reto_requerido"] is True
    # Terminal de confianza → no reto.
    mfa_dispositivos.registrar_confianza(UID, "TERM-X", E1)
    d = DEC.evaluar({"id": UID, "perfil": "OPERARIO"}, id_empresa=E1, codigo_terminal="TERM-X")
    assert d["reto_requerido"] is False and d["confiable"] is True
    # Contexto API → nunca reto humano.
    assert DEC.evaluar({"id": UID, "perfil": "OPERARIO"}, id_empresa=E1, contexto="api")["reto_requerido"] is False
    mfa.desactivar(UID)
