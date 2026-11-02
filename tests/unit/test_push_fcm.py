"""
Tests de push FCM — antihurto móvil (migración 0251).

Cubre: gateway degradable (simulado sin proyecto/credencial), envío real con `transport` inyectado (JWT
del service account + intercambio OAuth2 + POST a FCM, sin red ni coste), persistencia de tokens de
dispositivo (antes en memoria, ahora en `dispositivos_push`) y credencial FCM cifrada (nunca en claro).
"""

import json

import pytest

from src.services.mobile import fcm, fcm_config, push
from src.services.mobile.fcm import FCMGateway

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _clave_rsa_prueba():
    """Genera una clave RSA real (no un texto simulado) para que PyJWT pueda firmar el JWT del
    service account en los tests — PyJWT valida el PEM aunque el envío HTTP esté mockeado."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


SERVICE_ACCOUNT_FALSO = {
    "client_email": "test@demo-project.iam.gserviceaccount.com",
    "private_key": _clave_rsa_prueba(),
}


def test_gateway_degradable_sin_config():
    gw = FCMGateway(project_id=None, service_account_json=None, modo_simulado=False)
    assert gw.modo_simulado is True
    r = gw.enviar("token-x", "Titulo", "Cuerpo", datos={"ean": "ART1"})
    assert r["ok"] is True and r["detalle"] == "simulado"


def test_gateway_real_con_transport_inyectado():
    """`transport` inyectable permite probar el flujo OAuth2 + envío SIN red real (mismo patrón que
    `ESLGateway`). El JWT se firma con una clave RSA de prueba real (para que PyJWT no falle al firmar)."""
    cred = {"client_email": "test@demo.iam.gserviceaccount.com", "private_key": _clave_rsa_prueba()}

    llamadas = []

    def transport_falso(metodo, url, headers, cuerpo, es_form=False):
        llamadas.append((metodo, url, headers, cuerpo, es_form))
        if url == fcm._TOKEN_URL:
            return 200, json.dumps({"access_token": "ACCESS-123", "expires_in": 3600})
        assert "messages:send" in url
        assert headers["Authorization"] == "Bearer ACCESS-123"
        assert cuerpo["message"]["token"] == "tok-real"
        return 200, json.dumps({"name": "projects/demo/messages/1"})

    gw = FCMGateway(project_id="demo-project", service_account_json=cred, modo_simulado=False,
                     transport=transport_falso)
    assert gw.modo_simulado is False
    r = gw.enviar("tok-real", "Alerta", "Cuerpo", datos={"ean": "ART1", "precio": 9.99})
    assert r["ok"] is True
    assert llamadas[1][3]["message"]["notification"]["title"] == "Alerta"
    assert llamadas[1][3]["message"]["data"]["ean"] == "ART1"
    assert len(llamadas) == 2   # token-exchange + envío

    # segunda llamada reutiliza el access token cacheado (no repite el token-exchange)
    gw.enviar("tok-real", "Alerta 2", "Cuerpo 2", datos={})
    assert len(llamadas) == 3


def test_gateway_envio_fallido_no_inventa_exito():
    def transport_falso(metodo, url, headers, cuerpo, es_form=False):
        if url == fcm._TOKEN_URL:
            return 200, json.dumps({"access_token": "T", "expires_in": 3600})
        return 404, "NOT_FOUND: token de dispositivo inválido"

    gw = FCMGateway(project_id="demo", service_account_json=SERVICE_ACCOUNT_FALSO, modo_simulado=False,
                     transport=transport_falso)
    r = gw.enviar("tok-invalido", "T", "C")
    assert r["ok"] is False and "404" in r["motivo"]


def test_config_credencial_cifrada(fab, db):
    fab.al_limpiar(lambda: fab._exec("DELETE FROM fcm_config WHERE id=1"))
    assert fcm_config.guardar_config(
        project_id="demo-project", service_account_json=SERVICE_ACCOUNT_FALSO, modo_simulado=False)
    # en la BD la credencial NUNCA está en claro
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT service_account_cifrado FROM fcm_config WHERE id=1")
        raw = cur.fetchone()[0]
    assert raw and SERVICE_ACCOUNT_FALSO["client_email"] not in str(raw)
    # round-trip interno (uso del gateway) sí la recupera
    cfg = fcm_config.obtener_config(incluir_credencial=True)
    assert cfg["_service_account"]["client_email"] == SERVICE_ACCOUNT_FALSO["client_email"]
    # la vista pública no expone la credencial
    pub = fcm_config.obtener_config()
    assert "service_account_cifrado" not in pub and "_service_account" not in pub
    assert pub["tiene_credencial"] is True


def test_config_sin_datos_gateway_simulado(fab):
    fab._exec("DELETE FROM fcm_config WHERE id=1")
    gw = fcm_config.gateway()
    assert gw.modo_simulado is True


def test_registrar_y_listar_dispositivos(fab, emp, db):
    assert push.registrar_dispositivo("99", "tok-A", id_empresa=emp) is True
    fab._borrar("dispositivos_push", "token", "tok-A")
    assert "tok-A" in push.dispositivos("99", id_empresa=emp)
    # re-registrar el mismo token no duplica (ON DUPLICATE KEY)
    assert push.registrar_dispositivo("99", "tok-A", id_empresa=emp) is True
    assert push.dispositivos("99", id_empresa=emp).count("tok-A") == 1


def test_enviar_intenta_push_real_por_dispositivo(fab, emp, db):
    push.registrar_dispositivo("98", "tok-B", id_empresa=emp)
    fab._borrar("dispositivos_push", "token", "tok-B")
    fab._exec("DELETE FROM fcm_config WHERE id=1")   # sin config global → gateway simulado
    r = push.enviar("98", "Alerta", "Cuerpo", id_empresa=emp, datos={"ean": "X"})
    assert r["dispositivos"] == 1
    assert r["push_real"]["intentados"] == 1 and r["push_real"]["ok"] == 1
