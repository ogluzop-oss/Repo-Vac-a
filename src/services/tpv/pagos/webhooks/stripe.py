"""Verificador de webhook de Stripe.

Valida la cabecera `Stripe-Signature` (HMAC-SHA256 de "{t}.{payload}" con el
webhook secret `whsec_…`) y protege de replay con tolerancia de tiempo. Normaliza
el evento a pagado/fallido/pendiente. No confía en el cuerpo sin verificar.
"""

import hashlib
import hmac
import json
import logging
import time

from src.services.tpv.pagos.webhooks.base import VerificadorWebhook, resultado
from src.services.tpv.pagos.webhooks.registry import registrar_webhook

logger = logging.getLogger("pagos.webhooks.stripe")

_TOLERANCIA_S = 300
_PAGADO = {"checkout.session.completed", "payment_intent.succeeded", "charge.succeeded"}
_FALLIDO = {"payment_intent.payment_failed", "checkout.session.expired", "charge.failed"}


def verificar_firma_stripe(headers: dict, body: bytes, secret: str, tolerancia: int = _TOLERANCIA_S):
    """Valida la firma `Stripe-Signature` (HMAC-SHA256 + protección replay) y devuelve
    `(True, evento_dict)` o `(False, mensaje)`. Reutilizable por el checkout y por Connect (F3)."""
    if not secret:
        return False, "Falta el webhook secret de Stripe."
    firma = (headers or {}).get("Stripe-Signature") or (headers or {}).get("stripe-signature") or ""
    partes = dict(p.split("=", 1) for p in firma.split(",") if "=" in p)
    t = partes.get("t"); v1 = partes.get("v1")
    if not t or not v1:
        return False, "Cabecera Stripe-Signature inválida."
    try:
        if abs(time.time() - int(t)) > tolerancia:
            return False, "Evento fuera de la ventana de tiempo (replay)."
    except ValueError:
        return False, "Timestamp inválido."
    raw = body if isinstance(body, (bytes, bytearray)) else str(body).encode()
    firmado = t.encode() + b"." + raw
    esperado = hmac.new(secret.encode(), firmado, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado, v1):
        return False, "Firma de Stripe no válida."
    try:
        return True, json.loads(raw.decode("utf-8"))
    except Exception:
        return False, "Cuerpo JSON no válido."


@registrar_webhook("stripe")
class WebhookStripe(VerificadorWebhook):
    nombre = "stripe"

    def verificar(self, headers: dict, body: bytes, config: dict) -> dict:
        ok, ev = verificar_firma_stripe(headers, body, (config or {}).get("webhook_secret") or "")
        if not ok:
            return resultado(False, mensaje=ev)
        tipo = ev.get("type") or ""
        obj = (ev.get("data") or {}).get("object") or {}
        # Referencia: id de la sesión/intent (lo que guardamos como referencia_pago)
        # o nuestro client_reference_id (id_pedido) si viene.
        referencia = obj.get("id") or obj.get("client_reference_id")
        estado = "pagado" if tipo in _PAGADO else "fallido" if tipo in _FALLIDO else "pendiente"
        return resultado(True, estado=estado, referencia=referencia,
                         evento_id=ev.get("id"), evento_tipo=tipo,
                         mensaje="Firma Stripe verificada.")
