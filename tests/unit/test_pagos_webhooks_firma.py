"""Unit · verificación de firma de webhooks (Stripe/Redsys) — sin BD, deterministas."""

import base64
import hashlib
import hmac
import json
import time

import pytest

from src.services.tpv.pagos.redsys import _3des_cbc_encrypt
from src.services.tpv.pagos.webhooks.registry import verificador_de

pytestmark = pytest.mark.unit

_STRIPE_SECRET = "whsec_test_firma"


def _evento_stripe(ref="cs_test_1", tipo="checkout.session.completed", eid="evt_1"):
    return json.dumps({"id": eid, "type": tipo, "data": {"object": {"id": ref}}}).encode()


def _firma_stripe(body, t, secret=_STRIPE_SECRET):
    return hmac.new(secret.encode(), t.encode() + b"." + body, hashlib.sha256).hexdigest()


def test_stripe_firma_valida():
    v = verificador_de("stripe")
    body = _evento_stripe("cs_OK")
    t = str(int(time.time()))
    res = v.verificar({"Stripe-Signature": f"t={t},v1={_firma_stripe(body, t)}"},
                      body, {"webhook_secret": _STRIPE_SECRET})
    assert res["ok"] and res["estado"] == "pagado" and res["referencia"] == "cs_OK"


def test_stripe_firma_invalida():
    v = verificador_de("stripe")
    body = _evento_stripe()
    t = str(int(time.time()))
    res = v.verificar({"Stripe-Signature": f"t={t},v1=deadbeef"}, body,
                      {"webhook_secret": _STRIPE_SECRET})
    assert res["ok"] is False


def test_stripe_replay_timestamp_viejo():
    v = verificador_de("stripe")
    body = _evento_stripe()
    viejo = str(int(time.time()) - 9999)
    res = v.verificar({"Stripe-Signature": f"t={viejo},v1={_firma_stripe(body, viejo)}"},
                      body, {"webhook_secret": _STRIPE_SECRET})
    assert res["ok"] is False


def test_stripe_sin_secreto():
    v = verificador_de("stripe")
    res = v.verificar({"Stripe-Signature": "t=1,v1=x"}, _evento_stripe(), {})
    assert res["ok"] is False


def test_stripe_pago_fallido():
    v = verificador_de("stripe")
    body = _evento_stripe(tipo="payment_intent.payment_failed")
    t = str(int(time.time()))
    res = v.verificar({"Stripe-Signature": f"t={t},v1={_firma_stripe(body, t)}"},
                      body, {"webhook_secret": _STRIPE_SECRET})
    assert res["ok"] and res["estado"] == "fallido"


# ── Redsys ───────────────────────────────────────────────────────────────────
_REDSYS_SECRET = base64.b64encode(b"sq7HjrUOBfKmC576ILgskD5s").decode()


def _notif_redsys(order="abc123", response="0000"):
    params = {"Ds_Order": order, "Ds_Response": response}
    mp = base64.b64encode(json.dumps(params).encode()).decode()
    der = _3des_cbc_encrypt(base64.b64decode(_REDSYS_SECRET), order.encode())
    firma = base64.b64encode(hmac.new(der, mp.encode(), hashlib.sha256).digest()).decode()
    from urllib.parse import urlencode
    return urlencode({"Ds_MerchantParameters": mp, "Ds_Signature": firma}).encode()


def test_redsys_firma_valida():
    v = verificador_de("redsys")
    res = v.verificar({}, _notif_redsys("ord1", "0000"), {"api_secret": _REDSYS_SECRET})
    assert res["ok"] and res["estado"] == "pagado" and res["referencia"] == "ord1"


def test_redsys_denegada():
    v = verificador_de("redsys")
    res = v.verificar({}, _notif_redsys("ord2", "0190"), {"api_secret": _REDSYS_SECRET})
    assert res["ok"] and res["estado"] == "fallido"


def test_redsys_firma_manipulada():
    v = verificador_de("redsys")
    body = _notif_redsys("ord3").replace(b"Ds_Signature=", b"Ds_Signature=XX")
    res = v.verificar({}, body, {"api_secret": _REDSYS_SECRET})
    assert res["ok"] is False
