"""
Unit · `reembolsar()` real en las pasarelas del storefront (Stripe/PayPal/Redsys) — cierre de la
brecha del auto-reembolso de Click & Collect (antes degradaba siempre a "registrado" porque estas
tres clases no exponían el método). Sin red real: `requests` mockeado; sin credenciales
configuradas, cada gateway debe degradar a False SIN intentar red (seguro en CI/sin secretos).
"""

import base64
import hashlib
import hmac
import json

import pytest

from src.services.tpv.pagos.paypal import PasarelaPayPal
from src.services.tpv.pagos.redsys import PasarelaRedsys, _3des_cbc_encrypt
from src.services.tpv.pagos.stripe import PasarelaStripe

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text or json.dumps(self._data)

    def json(self):
        return self._data


# ── Stripe ───────────────────────────────────────────────────────────────────
def test_stripe_reembolsar_sin_credenciales_degrada_sin_red(monkeypatch):
    llamado = []
    monkeypatch.setattr("requests.get", lambda *a, **k: llamado.append(1))
    gw = PasarelaStripe({})
    assert gw.reembolsar("cs_test_1") is False
    assert llamado == []


def test_stripe_reembolsar_exito(monkeypatch):
    def fake_get(url, auth=None, timeout=None):
        return _Resp(200, {"payment_intent": "pi_123"})

    def fake_post(url, data=None, auth=None, timeout=None):
        assert data["payment_intent"] == "pi_123"
        return _Resp(200, {"id": "re_1"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    gw = PasarelaStripe({"api_key": "sk_test_x"})
    assert gw.reembolsar("cs_test_1", importe=15.0) is True


def test_stripe_reembolsar_sesion_sin_payment_intent(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp(200, {}))
    gw = PasarelaStripe({"api_key": "sk_test_x"})
    assert gw.reembolsar("cs_test_1") is False


def test_stripe_reembolsar_rechazo_de_la_pasarela(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp(200, {"payment_intent": "pi_123"}))
    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp(402, {}, text="insufficient funds"))
    gw = PasarelaStripe({"api_key": "sk_test_x"})
    assert gw.reembolsar("cs_test_1") is False


# ── PayPal ───────────────────────────────────────────────────────────────────
def test_paypal_reembolsar_sin_credenciales_degrada_sin_red(monkeypatch):
    llamado = []
    monkeypatch.setattr("requests.post", lambda *a, **k: llamado.append(1))
    gw = PasarelaPayPal({})
    assert gw.reembolsar("ORDER-1") is False
    assert llamado == []


def test_paypal_reembolsar_exito(monkeypatch):
    def fake_post(url, data=None, json=None, headers=None, timeout=None, auth=None):
        if url.endswith("/v1/oauth2/token"):
            return _Resp(200, {"access_token": "tok"})
        assert url.endswith("/v2/payments/captures/CAP-1/refund")
        return _Resp(201, {"id": "refund-1"})

    def fake_get(url, headers=None, timeout=None):
        return _Resp(200, {"purchase_units": [{"payments": {"captures": [{"id": "CAP-1"}]}}]})

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)
    gw = PasarelaPayPal({"api_key": "cid", "api_secret": "secret"})
    assert gw.reembolsar("ORDER-1", importe=9.5) is True


def test_paypal_reembolsar_sin_captura(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp(200, {"access_token": "tok"}))
    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp(200, {"purchase_units": [{}]}))
    gw = PasarelaPayPal({"api_key": "cid", "api_secret": "secret"})
    assert gw.reembolsar("ORDER-1") is False


def test_paypal_reembolsar_sin_token(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp(401, {}))
    gw = PasarelaPayPal({"api_key": "cid", "api_secret": "secret"})
    assert gw.reembolsar("ORDER-1") is False


# ── Redsys ───────────────────────────────────────────────────────────────────
_REDSYS_SECRET_B64 = base64.b64encode(b"sq7HjrUOBfKmC576ILgskD5s").decode()


def _config_redsys():
    return {"api_secret": _REDSYS_SECRET_B64, "comercio": "999008881", "api_key": "1"}


def _resp_redsys(order, ds_response="0000", secreto_b64=_REDSYS_SECRET_B64, firmar_con=None):
    """Construye una respuesta REST de Redsys firmada (igual patrón que el webhook)."""
    datos = {"Ds_Order": order, "Ds_Response": ds_response}
    mp = base64.b64encode(json.dumps(datos).encode()).decode()
    clave = base64.b64decode(firmar_con or secreto_b64)
    derived = _3des_cbc_encrypt(clave, order.encode())
    firma = base64.b64encode(hmac.new(derived, mp.encode(), hashlib.sha256).digest()).decode()
    return {"Ds_SignatureVersion": "HMAC_SHA256_V1", "Ds_MerchantParameters": mp,
           "Ds_Signature": firma}


def test_redsys_reembolsar_sin_credenciales_degrada_sin_red(monkeypatch):
    llamado = []
    monkeypatch.setattr("requests.post", lambda *a, **k: llamado.append(1))
    gw = PasarelaRedsys({})
    assert gw.reembolsar("000001", importe=10.0) is False
    assert llamado == []


def test_redsys_reembolsar_sin_importe_falla_honesto():
    gw = PasarelaRedsys(_config_redsys())
    assert gw.reembolsar("000001") is False


def test_redsys_reembolsar_exito(monkeypatch):
    order = "000001"

    def fake_post(url, json=None, timeout=None):
        assert url.endswith("/trataPeticionREST")
        return _Resp(200, _resp_redsys(order, "0000"))

    monkeypatch.setattr("requests.post", fake_post)
    gw = PasarelaRedsys(_config_redsys())
    assert gw.reembolsar(order, importe=25.0) is True


def test_redsys_reembolsar_denegada(monkeypatch):
    order = "000002"
    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp(200, _resp_redsys(order, "0180")))
    gw = PasarelaRedsys(_config_redsys())
    assert gw.reembolsar(order, importe=25.0) is False


def test_redsys_reembolsar_firma_de_respuesta_invalida(monkeypatch):
    order = "000003"
    # Firmada con una clave DISTINTA a la configurada -> firma no coincide al verificar.
    otra_clave = base64.b64encode(b"OTRA_CLAVE_DE_COMERCIO_16").decode()
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: _Resp(200, _resp_redsys(order, "0000", firmar_con=otra_clave)))
    gw = PasarelaRedsys(_config_redsys())
    assert gw.reembolsar(order, importe=25.0) is False
