"""Pasarela Stripe (Checkout Sessions, cobro real).

api_key = Secret key (sk_test_… / sk_live_…). Crea una Checkout Session
(POST /v1/checkout/sessions) y devuelve la URL hospedada de pago; verificar_pago
consulta el payment_status de la sesión. Degrada con elegancia.
"""

import logging

from src.services.tpv.pagos.base import PasarelaPago

logger = logging.getLogger("pagos.stripe")

_API = "https://api.stripe.com/v1"


class PasarelaStripe(PasarelaPago):
    nombre = "stripe"

    def configurado(self) -> bool:
        return bool(self.config.get("api_key"))

    def crear_cobro(self, pedido: dict) -> dict:
        if not self.configurado():
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": "Stripe no configurado."}
        try:
            import requests
        except Exception:
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": "requests no disponible."}
        total = float(pedido.get("total") or 0)
        # Stripe trabaja en la unidad mínima (céntimos).
        importe = int(round(total * 100))
        ref_local = str(pedido.get("id_pedido") or "")
        # Form-encoded (API de Stripe). Una sola línea con el total del pedido.
        data = {
            "mode": "payment",
            "success_url": "https://pago.local/ok?ref=" + ref_local,
            "cancel_url": "https://pago.local/ko?ref=" + ref_local,
            "client_reference_id": ref_local,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": self.moneda().lower(),
            "line_items[0][price_data][unit_amount]": str(importe),
            "line_items[0][price_data][product_data][name]": f"Pedido {ref_local[:8]}",
        }
        try:
            r = requests.post(f"{_API}/checkout/sessions", data=data,
                              auth=(self.config["api_key"], ""), timeout=20)
            if r.status_code in (200, 201):
                j = r.json()
                return {"ok": True, "url": j.get("url") or "", "referencia": j.get("id") or "",
                        "estado": "pendiente", "mensaje": "Sesión de pago creada."}
            logger.warning("Stripe %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": f"Stripe respondió {r.status_code}."}
        except Exception as e:
            logger.warning("Stripe crear_cobro: %s", e)
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": f"Error Stripe: {e}"}

    def verificar_pago(self, referencia: str) -> str:
        if not self.configurado() or not referencia:
            return "pendiente"
        try:
            import requests
            r = requests.get(f"{_API}/checkout/sessions/{referencia}",
                             auth=(self.config["api_key"], ""), timeout=20)
            if r.status_code == 200:
                estado = (r.json().get("payment_status") or "").lower()
                return "pagado" if estado == "paid" else "pendiente"
        except Exception as e:
            logger.warning("Stripe verificar_pago: %s", e)
        return "pendiente"
