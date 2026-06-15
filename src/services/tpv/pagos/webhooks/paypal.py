"""Verificador de webhook de PayPal.

PayPal valida la autenticidad mediante su API oficial
(/v1/notifications/verify-webhook-signature) con las cabeceras de transmisión y
el `webhook_id` (guardado en webhook_secret). Si no se puede verificar (sin
credenciales/red), se RECHAZA el evento (no se confía en el cuerpo a ciegas).
"""

import json
import logging

from src.services.tpv.pagos.webhooks.base import VerificadorWebhook, resultado
from src.services.tpv.pagos.webhooks.registry import registrar_webhook

logger = logging.getLogger("pagos.webhooks.paypal")

_PAGADO = {"PAYMENT.CAPTURE.COMPLETED", "CHECKOUT.ORDER.APPROVED",
           "PAYMENT.SALE.COMPLETED"}
_FALLIDO = {"PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED",
            "PAYMENT.CAPTURE.REVERSED", "CHECKOUT.ORDER.DECLINED"}


@registrar_webhook("paypal")
class WebhookPayPal(VerificadorWebhook):
    nombre = "paypal"

    def verificar(self, headers: dict, body: bytes, config: dict) -> dict:
        webhook_id = (config or {}).get("webhook_secret") or ""
        if not webhook_id:
            return resultado(False, mensaje="Falta el webhook_id de PayPal.")
        raw = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
        try:
            evento = json.loads(raw)
        except Exception:
            return resultado(False, mensaje="Cuerpo JSON de PayPal no válido.")
        h = {k.lower(): v for k, v in (headers or {}).items()}
        if not self._verificar_api(h, evento, webhook_id, config):
            return resultado(False, mensaje="No se pudo verificar la firma de PayPal.")
        tipo = evento.get("event_type") or ""
        recurso = evento.get("resource") or {}
        referencia = (((recurso.get("supplementary_data") or {}).get("related_ids") or {})
                      .get("order_id") or recurso.get("id"))
        estado = "pagado" if tipo in _PAGADO else "fallido" if tipo in _FALLIDO else "pendiente"
        return resultado(True, estado=estado, referencia=referencia,
                         evento_id=evento.get("id"), evento_tipo=tipo,
                         mensaje="Firma PayPal verificada.")

    @staticmethod
    def _verificar_api(h, evento, webhook_id, config) -> bool:
        try:
            import requests
            from src.services.tpv.pagos.paypal import PasarelaPayPal
        except Exception:
            return False
        pp = PasarelaPayPal(config or {})
        base = pp._base()
        token = pp._token(base)
        if not token:
            return False
        payload = {
            "transmission_id": h.get("paypal-transmission-id"),
            "transmission_time": h.get("paypal-transmission-time"),
            "cert_url": h.get("paypal-cert-url"),
            "auth_algo": h.get("paypal-auth-algo"),
            "transmission_sig": h.get("paypal-transmission-sig"),
            "webhook_id": webhook_id,
            "webhook_event": evento,
        }
        if not all((payload["transmission_id"], payload["transmission_sig"],
                    payload["cert_url"])):
            return False
        try:
            r = requests.post(f"{base}/v1/notifications/verify-webhook-signature",
                              json=payload, headers={"Authorization": f"Bearer {token}"},
                              timeout=20)
            return (r.status_code == 200
                    and (r.json().get("verification_status") == "SUCCESS"))
        except Exception as e:
            logger.warning("PayPal verify-webhook-signature: %s", e)
            return False
