"""Pasarela PayPal (Orders v2, cobro real).

api_key = Client ID, api_secret = Secret. Obtiene un token OAuth2, crea una orden
(POST /v2/checkout/orders) y devuelve el enlace de aprobación; verificar_pago
consulta el estado de la orden (COMPLETED/APPROVED → pagado). modo test → sandbox.
Degrada con elegancia.
"""

import logging

from src.services.tpv.pagos.base import PasarelaPago

logger = logging.getLogger("pagos.paypal")


class PasarelaPayPal(PasarelaPago):
    nombre = "paypal"

    def _base(self):
        return ("https://api-m.sandbox.paypal.com" if self.es_test()
                else "https://api-m.paypal.com")

    def configurado(self) -> bool:
        return bool(self.config.get("api_key") and self.config.get("api_secret"))

    def _token(self, base):
        import requests
        r = requests.post(f"{base}/v1/oauth2/token",
                          data={"grant_type": "client_credentials"},
                          auth=(self.config["api_key"], self.config["api_secret"]),
                          timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token")
        logger.warning("PayPal token %s: %s", r.status_code, r.text[:160])
        return None

    def crear_cobro(self, pedido: dict) -> dict:
        if not self.configurado():
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": "PayPal no configurado."}
        try:
            import requests
        except Exception:
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": "requests no disponible."}
        base = self._base()
        try:
            token = self._token(base)
            if not token:
                return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                        "mensaje": "PayPal: token no obtenido."}
            total = float(pedido.get("total") or 0)
            payload = {"intent": "CAPTURE", "purchase_units": [{
                "reference_id": str(pedido.get("id_pedido") or ""),
                "amount": {"currency_code": self.moneda(), "value": f"{total:.2f}"}}]}
            r = requests.post(f"{base}/v2/checkout/orders", json=payload,
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json"}, timeout=20)
            if r.status_code in (200, 201):
                j = r.json()
                url = next((l.get("href") for l in j.get("links", [])
                            if l.get("rel") == "approve"), "")
                return {"ok": True, "url": url, "referencia": j.get("id") or "",
                        "estado": "pendiente", "mensaje": "Orden PayPal creada."}
            logger.warning("PayPal %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": f"PayPal respondió {r.status_code}."}
        except Exception as e:
            logger.warning("PayPal crear_cobro: %s", e)
            return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                    "mensaje": f"Error PayPal: {e}"}

    def verificar_pago(self, referencia: str) -> str:
        if not self.configurado() or not referencia:
            return "pendiente"
        try:
            import requests
            base = self._base()
            token = self._token(base)
            if not token:
                return "pendiente"
            r = requests.get(f"{base}/v2/checkout/orders/{referencia}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=20)
            if r.status_code == 200:
                estado = (r.json().get("status") or "").upper()
                return "pagado" if estado in ("COMPLETED", "APPROVED") else "pendiente"
        except Exception as e:
            logger.warning("PayPal verificar_pago: %s", e)
        return "pendiente"
