"""Marketplace + Pagos (F3) — webhooks de Stripe Connect. (unit, sin db)

Cubre: rechazo por firma inválida; idempotencia (evento duplicado); y el despacho de los eventos Connect a
la sincronización de cuentas (account.updated) y a las transiciones de escrow (retención/liberación/disputa/
reembolso). La firma HMAC se genera igual que Stripe; la BD se aísla por monkeypatch.
"""

import hashlib
import hmac
import json
import time

import pytest

from src.services.pagos_marketplace import webhooks as WH

SECRET = "whsec_test_f3"


def _firmar(evento: dict, secret=SECRET):
    raw = json.dumps(evento).encode()
    t = str(int(time.time()))
    sig = hmac.new(secret.encode(), t.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, {"Stripe-Signature": f"t={t},v1={sig}"}


@pytest.fixture
def _aislar(monkeypatch):
    """Config con secret Connect + idempotencia en memoria + captura de las acciones despachadas."""
    import src.db.pagos_webhooks as wlog
    from src.services.pagos_marketplace import cuentas, escrow, psp

    monkeypatch.setattr(psp, "config_plataforma", lambda: {"webhook_secret_connect": SECRET})
    vistos = set()

    def _reclamar(proveedor, evento_id, **kw):
        if evento_id in vistos:
            return None
        vistos.add(evento_id)
        return len(vistos)
    monkeypatch.setattr(wlog, "reclamar_evento", _reclamar)
    monkeypatch.setattr(wlog, "actualizar_evento", lambda *a, **k: None)

    llamadas = {"sync": [], "estado": []}
    monkeypatch.setattr(cuentas, "sincronizar_estado",
                        lambda acct, **kw: llamadas["sync"].append((acct, kw)) or True)
    monkeypatch.setattr(escrow, "tx_por_payment_ref", lambda ref: {"id": 42} if ref else None)
    monkeypatch.setattr(escrow, "set_estado_local",
                        lambda txid, nuevo, **kw: llamadas["estado"].append((txid, nuevo)) or {"ok": True})
    return llamadas


def test_firma_invalida_rechaza(_aislar):
    raw, _ = _firmar({"id": "evt_1", "type": "account.updated", "data": {"object": {"id": "acct_x"}}})
    res = WH.procesar_webhook_connect({"Stripe-Signature": "t=1,v1=deadbeef"}, raw, id_empresa="E1")
    assert res["ok"] is False and res["http"] == 400


def test_account_updated_sincroniza(_aislar):
    ev = {"id": "evt_acc", "type": "account.updated", "data": {"object": {
        "id": "acct_9", "payouts_enabled": True, "charges_enabled": True,
        "external_accounts": {"data": [{"bank_name": "CaixaBank", "last4": "1332"}]}}}}
    raw, hdr = _firmar(ev)
    res = WH.procesar_webhook_connect(hdr, raw, id_empresa="E1")
    assert res["ok"] and res["accion"] == "account_synced"
    acct, kw = _aislar["sync"][0]
    assert acct == "acct_9" and kw["status"] == "verified"
    assert kw["banco"] == "CaixaBank" and kw["ultimos4"] == "1332"


def test_evento_duplicado_idempotente(_aislar):
    ev = {"id": "evt_dup", "type": "account.updated", "data": {"object": {"id": "acct_1"}}}
    raw, hdr = _firmar(ev)
    assert WH.procesar_webhook_connect(hdr, raw, id_empresa="E1")["duplicado"] is False
    # Segundo idéntico → duplicado (no vuelve a despachar).
    raw2, hdr2 = _firmar(ev)
    assert WH.procesar_webhook_connect(hdr2, raw2, id_empresa="E1")["duplicado"] is True


@pytest.mark.parametrize("tipo,esperado", [
    ("payment_intent.amount_capturable_updated", "FUNDS_HELD"),
    ("payment_intent.succeeded", "FUNDS_RELEASED"),
    ("charge.dispute.created", "IN_DISPUTE"),
    ("charge.refunded", "REFUNDED"),
])
def test_eventos_escrow_transicionan(_aislar, tipo, esperado):
    obj = {"id": "pi_123"} if tipo.startswith("payment_intent") else {"payment_intent": "pi_123"}
    ev = {"id": f"evt_{tipo}", "type": tipo, "data": {"object": obj}}
    raw, hdr = _firmar(ev)
    res = WH.procesar_webhook_connect(hdr, raw, id_empresa="E1")
    assert res["ok"]
    assert _aislar["estado"][-1] == (42, esperado)
