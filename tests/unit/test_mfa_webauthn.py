"""
Tests · WebAuthn / Passkeys (Fase 5) — capa relying party. Verifica la disponibilidad de la librería,
la recomendación por rol, la generación de opciones (con challenge) + reto firmado, el manejo
controlado de respuestas inválidas, y el almacenamiento/listado/revocación (solo datos públicos).
La ceremonia real es de navegador; aquí se prueba la infraestructura del servidor.
"""

import pytest

pytestmark = pytest.mark.db

# WebAuthn es un método OPCIONAL degradable: si la librería no está provista, se omite este módulo
# (la feature sigue degradando limpiamente vía `disponible()`; TOTP continúa como fallback).
pytest.importorskip("webauthn")

UID = "888010"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM mfa_webauthn_credenciales WHERE id_usuario=%s", (UID,))
            c.commit()
    _b()
    yield
    _b()


def test_disponible_y_recomendado():
    from src.services.seguridad import mfa_webauthn as W
    assert W.disponible() is True   # librería `webauthn` instalada (Fase 5)
    assert W.webauthn_recomendado("ADMINISTRADOR") is True
    assert W.webauthn_recomendado("SUPERADMIN") is True
    assert W.webauthn_recomendado("OPERARIO") is False


def test_iniciar_registro_opciones_y_reto(limpia):
    from src.services.seguridad import mfa_webauthn as W
    r = W.iniciar_registro({"id": UID, "nombre": "t", "id_empresa": None})
    assert r["ok"] is True
    assert "challenge" in r["options"]                      # opciones para navigator.credentials.create
    assert W._verificar_reto(r["reto"]) is not None          # el reto firmado se valida
    assert W._verificar_reto(r["reto"] + "x") is None        # firma manipulada → rechazada


def test_respuesta_invalida_controlada(limpia):
    from src.services.seguridad import mfa_webauthn as W
    r = W.iniciar_registro({"id": UID, "nombre": "t"})
    out = W.confirmar_registro({"id": UID}, r["reto"], {"id": "x", "response": {}})
    assert out["ok"] is False and out["error"] in ("verificacion_fallida", "reto_invalido")


def test_storage_listar_revocar(limpia, db):
    from src.services.seguridad import mfa_webauthn as W
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("INSERT INTO mfa_webauthn_credenciales (id_usuario, credential_id, public_key, "
                    "sign_count, nombre) VALUES (%s,%s,%s,0,%s)", (UID, "CID1", "PUB1", "Mi llave"))
        c.commit()
    lst = W.listar(UID)
    assert len(lst) == 1 and lst[0]["nombre"] == "Mi llave"
    assert W.iniciar_login({"id": UID})["ok"] is True        # hay allow_credentials
    assert W.revocar(lst[0]["id"])["ok"] is True
    assert W.listar(UID) == []
