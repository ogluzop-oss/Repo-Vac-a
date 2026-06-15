"""Integración · handler de webhooks: firma→idempotencia→localizar pedido→PAGADO."""

import hashlib
import hmac
import json
import os
import time

import pytest

pytestmark = pytest.mark.db

_SECRET = "whsec_int"


def _stripe(body, t, secret=_SECRET):
    return hmac.new(secret.encode(), t.encode() + b"." + body, hashlib.sha256).hexdigest()


def _evt(ref, eid):
    return json.dumps({"id": eid, "type": "checkout.session.completed",
                       "data": {"object": {"id": ref}}}).encode()


def _estado(db, pid):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT estado, estado_pago FROM pedidos_online WHERE id_pedido=%s", (pid,))
        return cur.fetchone()


def _limpia_docs(fab, pid):
    fab.al_limpiar(lambda: [os.remove(f) for pre in ("justificante_pago",)
                            if os.path.exists(f := os.path.join("documentos", "pedidos", f"{pre}_{pid}.pdf"))])


def test_webhook_marca_pagado(db, fab):
    from src.services.tpv.pagos import webhooks as wh
    fab.pasarela(webhook_secret=_SECRET)
    ref = "cs_" + os.urandom(4).hex()
    pid = fab.pedido_online(referencia_pago=ref)
    _limpia_docs(fab, pid)
    body = _evt(ref, "evt_" + os.urandom(4).hex())
    t = str(int(time.time()))
    r = wh.procesar_webhook("stripe", {"Stripe-Signature": f"t={t},v1={_stripe(body, t)}"},
                            body, id_empresa=fab.EMP_DEFECTO, ip_origen="1.1.1.1")
    assert r["ok"] and r["id_pedido"] == pid
    assert _estado(db, pid) == ("PAGADO", "pagado")


def test_webhook_duplicado_idempotente(db, fab):
    from src.services.tpv.pagos import webhooks as wh
    fab.pasarela(webhook_secret=_SECRET)
    ref = "cs_" + os.urandom(4).hex()
    pid = fab.pedido_online(referencia_pago=ref)
    _limpia_docs(fab, pid)
    body = _evt(ref, "evt_dup")
    t = str(int(time.time()))
    hdr = {"Stripe-Signature": f"t={t},v1={_stripe(body, t)}"}
    wh.procesar_webhook("stripe", hdr, body, id_empresa=fab.EMP_DEFECTO)
    r2 = wh.procesar_webhook("stripe", hdr, body, id_empresa=fab.EMP_DEFECTO)
    assert r2.get("duplicado") is True


def test_webhook_firma_invalida_rechaza(db, fab):
    from src.services.tpv.pagos import webhooks as wh
    fab.pasarela(webhook_secret=_SECRET)
    ref = "cs_" + os.urandom(4).hex()
    fab.pedido_online(referencia_pago=ref)
    body = _evt(ref, "evt_bad")
    r = wh.procesar_webhook("stripe", {"Stripe-Signature": "t=1,v1=bad"}, body,
                            id_empresa=fab.EMP_DEFECTO)
    assert r["ok"] is False and r["http"] == 400


def test_webhook_aislamiento_multiempresa(db, fab):
    from src.services.tpv.pagos import webhooks as wh
    emp_b = fab.empresa("EMP B")
    fab.pasarela(id_empresa=emp_b, webhook_secret=_SECRET)
    ref = "cs_" + os.urandom(4).hex()
    fab.pedido_online(id_empresa=fab.EMP_DEFECTO, referencia_pago=ref)   # pedido de empresa A
    body = _evt(ref, "evt_iso")
    t = str(int(time.time()))
    # Webhook llega para empresa B → no debe localizar el pedido de A.
    r = wh.procesar_webhook("stripe", {"Stripe-Signature": f"t={t},v1={_stripe(body, t)}"},
                            body, id_empresa=emp_b)
    assert r["ok"] and r.get("id_pedido") is None
