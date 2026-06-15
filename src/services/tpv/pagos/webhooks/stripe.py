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


@registrar_webhook("stripe")
class WebhookStripe(VerificadorWebhook):
    nombre = "stripe"

    def verificar(self, headers: dict, body: bytes, config: dict) -> dict:
        secret = (config or {}).get("webhook_secret") or ""
        if not secret:
            return resultado(False, mensaje="Falta el webhook secret de Stripe.")
        firma = (headers or {}).get("Stripe-Signature") or (headers or {}).get("stripe-signature") or ""
        partes = dict(p.split("=", 1) for p in firma.split(",") if "=" in p)
        t = partes.get("t"); v1 = partes.get("v1")
        if not t or not v1:
            return resultado(False, mensaje="Cabecera Stripe-Signature inválida.")
        # Protección replay: descarta firmas fuera de la ventana de tolerancia.
        try:
            if abs(time.time() - int(t)) > _TOLERANCIA_S:
                return resultado(False, mensaje="Evento fuera de la ventana de tiempo (replay).")
        except ValueError:
            return resultado(False, mensaje="Timestamp inválido.")
        raw = body if isinstance(body, (bytes, bytearray)) else str(body).encode()
        firmado = t.encode() + b"." + raw
        esperado = hmac.new(secret.encode(), firmado, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperado, v1):
            return resultado(False, mensaje="Firma de Stripe no válida.")
        try:
            evento = json.loads(raw.decode("utf-8"))
        except Exception:
            return resultado(False, mensaje="Cuerpo JSON no válido.")
        tipo = evento.get("type") or ""
        obj = (evento.get("data") or {}).get("object") or {}
        # Referencia: id de la sesión/intent (lo que guardamos como referencia_pago)
        # o nuestro client_reference_id (id_pedido) si viene.
        referencia = obj.get("id") or obj.get("client_reference_id")
        estado = "pagado" if tipo in _PAGADO else "fallido" if tipo in _FALLIDO else "pendiente"
        return resultado(True, estado=estado, referencia=referencia,
                         evento_id=evento.get("id"), evento_tipo=tipo,
                         mensaje="Firma Stripe verificada.")
