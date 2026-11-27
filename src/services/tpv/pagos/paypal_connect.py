"""
Pasarela PayPal para el marketplace B2B — pago DIRECTO, sin Partner Program NI custodia de Smart
Manager (rediseño explícito, 2026-11-27). El diseño anterior (custodia propia + Payout NETO,
2026-11-23) cobraba siempre a la cuenta de PayPal de Smart Manager y dependía de que PayPal
concediera el permiso de Payouts — bloqueado en producción con 403 AUTHORIZATION_ERROR. La API de
Órdenes de PayPal no permite dirigir el cobro a la cuenta de un TERCERO (`payee`) sin aprobación de
partner/marketplace (eso ya se había descartado); la única vía sin Partner Program es que la propia
Orden se cree y capture con las credenciales del DESTINATARIO final.

Modelo actual ("Opción B", pago directo): esta clase se instancia con las credenciales (`api_key`/
`api_secret`) del PROVEEDOR CONCRETO de cada transacción (ver `b2b_escrow._pasarela`, que las
resuelve vía `suministradores.credenciales_paypal_de` — nunca con las credenciales globales de
Smart Manager para este flujo). Como la app que crea la Orden es la del propio proveedor, el dinero
nace y vive en SU cuenta desde el `AUTHORIZE` inicial — `liberar_fondos` solo CAPTURA esa
autorización (ya en la cuenta del proveedor); no hay ningún Payout ni reparto posterior, porque
nunca hubo custodia que repartir. La comisión de plataforma (B2B, hoy siempre 0% — ver
`comisiones_b2b.py`) se cobra, si corresponde, por Stripe directo a cada parte, nunca aquí.

Config esperada: `api_key` (Client ID) + `api_secret` (Secret) — las del PROVEEDOR, no las de Smart
Manager. `modo` (test/live). DEGRADABLE: sin las 2 credenciales, `configurado()` es False y el
resolver cae al simulado — nunca se inventa un estado real.
"""

import logging

from src.services.tpv.pagos.base_marketplace import PasarelaMarketplace
from src.services.tpv.pagos.registry import registrar

logger = logging.getLogger("pagos.paypal_connect")


@registrar("paypal_connect", "PayPal (pago directo al proveedor)", orden=26)
class PasarelaPayPalConnect(PasarelaMarketplace):
    nombre = "paypal_connect"

    def _base(self):
        return ("https://api-m.sandbox.paypal.com" if self.es_test()
                else "https://api-m.paypal.com")

    def configurado(self) -> bool:
        return bool(self.config.get("api_key") and self.config.get("api_secret"))

    @staticmethod
    def _req():
        import requests  # import perezoso (degradable)
        return requests

    def _token(self):
        requests = self._req()
        r = requests.post(f"{self._base()}/v1/oauth2/token",
                          data={"grant_type": "client_credentials"},
                          auth=(self.config["api_key"], self.config["api_secret"]), timeout=20)
        if r.status_code == 200:
            return r.json().get("access_token")
        logger.warning("PayPal Connect token %s: %s", r.status_code, r.text[:200])
        return None

    def _headers(self, token, idem_key=None):
        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if idem_key:
            h["PayPal-Request-Id"] = idem_key
        return h

    # ── Escrow (Orders v2, intent=AUTHORIZE) — SIEMPRE contra la propia cuenta de Smart Manager ──
    def retener_fondos(self, *, importe, divisa="EUR", vendedor_account=None, comision=0,
                       referencia=None, idem_key=None, id_empresa=None, vault_id=None, **kw) -> dict:
        """`vendedor_account`/`comision` se ignoran aquí a propósito: esta instancia YA está
        autenticada como la app del proveedor (ver docstring del módulo) — la orden se crea
        directamente contra SU cuenta, no hace falta repartir nada dentro de ella.

        `vault_id` (token de la Vault API v3 del comprador PARA ESTE PROVEEDOR EN CONCRETO — ver
        `b2b_pago_comprador.iniciar_vinculacion_paypal_proveedor`): sin él, PayPal exigiría que el
        comprador aprobara el pago a mano en cada pedido — se rechaza explícitamente en vez de
        crear una orden que se quedaría colgada sin aprobar."""
        if not self.configurado():
            return {"ok": False, "mensaje": "PayPal no configurado."}
        if not vault_id:
            return {"ok": False, "mensaje": "Falta el método de pago PayPal guardado del comprador."}
        try:
            requests = self._req()
        except Exception:
            return {"ok": False, "mensaje": "requests no disponible."}
        token = self._token()
        if not token:
            return {"ok": False, "mensaje": "PayPal: no se pudo autenticar."}
        total = f"{float(importe):.2f}"
        divisa = (divisa or "EUR").upper()
        payload = {
            "intent": "AUTHORIZE",
            "purchase_units": [{
                "reference_id": str(referencia or "default"),
                "amount": {"currency_code": divisa, "value": total},
            }],
            "payment_source": {"paypal": {"vault_id": vault_id}},
        }
        try:
            r = requests.post(f"{self._base()}/v2/checkout/orders", json=payload,
                              headers=self._headers(token, idem_key), timeout=25)
            if r.status_code not in (200, 201):
                logger.warning("PayPal orders (AUTHORIZE) %s: %s", r.status_code, r.text[:200])
                return {"ok": False, "mensaje": f"PayPal {r.status_code}."}
            j = r.json()
            order_id = j.get("id")
            # APPROVED (lo esperado con vault_id) o COMPLETED (consentimiento previo): en ambos
            # casos hay que autorizar explícitamente para obtener el id de AUTHORIZATION que
            # `liberar_fondos`/`cancelar` necesitan — mismo "capture_method=manual" que Stripe.
            return self._autorizar_orden(order_id, token, idem_key)
        except Exception as e:
            logger.warning("retener_fondos (PayPal): %s", e)
            return {"ok": False, "mensaje": str(e)}

    def _autorizar_orden(self, order_id, token, idem_key) -> dict:
        requests = self._req()
        try:
            r = requests.post(f"{self._base()}/v2/checkout/orders/{order_id}/authorize",
                              headers=self._headers(token, idem_key), timeout=25)
            if r.status_code not in (200, 201):
                logger.warning("PayPal authorize %s: %s", r.status_code, r.text[:200])
                return {"ok": False, "mensaje": f"PayPal {r.status_code}."}
            j = r.json()
            autorizaciones = (((j.get("purchase_units") or [{}])[0].get("payments") or {})
                              .get("authorizations") or [])
            if not autorizaciones:
                return {"ok": False, "mensaje": "PayPal no devolvió ninguna autorización."}
            auth_id = autorizaciones[0].get("id")
            return {"ok": True, "payment_ref": auth_id, "estado": "PAYMENT_PENDING"}
        except Exception as e:
            logger.warning("_autorizar_orden: %s", e)
            return {"ok": False, "mensaje": str(e)}

    def obtener_payment_intent(self, payment_ref) -> dict:
        """`payment_ref` es el id de la AUTHORIZATION (ver `retener_fondos`)."""
        if not self.configurado() or not payment_ref:
            return {"ok": False, "mensaje": "PayPal no configurado o falta referencia."}
        try:
            requests = self._req()
            token = self._token()
            if not token:
                return {"ok": False, "mensaje": "PayPal: no se pudo autenticar."}
            r = requests.get(f"{self._base()}/v2/payments/authorizations/{payment_ref}",
                             headers=self._headers(token), timeout=25)
            if r.status_code == 200:
                j = r.json()
                estado_paypal = (j.get("status") or "").upper()
                # Traducido a vocabulario Stripe-like (lo que ya espera `b2b_escrow.
                # confirmar_pago_tras_retorno`): CREATED/PENDING ~ requires_capture, CAPTURED ~
                # succeeded — nunca se inventa un estado intermedio que PayPal no haya confirmado.
                status = {"CREATED": "requires_capture", "PENDING": "requires_capture",
                         "CAPTURED": "succeeded", "DENIED": "canceled",
                         "VOIDED": "canceled"}.get(estado_paypal, estado_paypal.lower())
                return {"ok": True, "status": status}
            return {"ok": False, "mensaje": f"PayPal {r.status_code}."}
        except Exception as e:
            logger.warning("obtener_payment_intent (PayPal): %s", e)
            return {"ok": False, "mensaje": str(e)}

    def liberar_fondos(self, *, payment_ref, idem_key=None, **kw) -> dict:
        """Captura la autorización — como la Orden se creó con las credenciales del PROVEEDOR
        (ver docstring del módulo), el dinero YA está en su cuenta desde el `AUTHORIZE`; capturar
        solo confirma el cargo final, nunca mueve fondos hacia Smart Manager ni hace falta ningún
        Payout posterior (a diferencia del modelo de custodia anterior, retirado 2026-11-27).
        `**kw` absorbe parámetros heredados de otras pasarelas (p. ej. `vendedor_account` de
        Stripe) que aquí ya no significan nada."""
        if not self.configurado():
            return {"ok": False, "mensaje": "PayPal no configurado."}
        if not payment_ref:
            return {"ok": False, "mensaje": "Falta la referencia de pago."}
        try:
            requests = self._req()
            token = self._token()
            if not token:
                return {"ok": False, "mensaje": "PayPal: no se pudo autenticar."}
            r = requests.post(f"{self._base()}/v2/payments/authorizations/{payment_ref}/capture",
                              json={}, headers=self._headers(token, idem_key), timeout=25)
            if r.status_code not in (200, 201):
                logger.warning("liberar_fondos (PayPal, captura) %s: %s", r.status_code, r.text[:200])
                return {"ok": False, "mensaje": f"PayPal {r.status_code}."}
            j = r.json()
            capture_ref = j.get("id") or payment_ref
        except Exception as e:
            logger.warning("liberar_fondos (PayPal, captura): %s", e)
            return {"ok": False, "mensaje": str(e)}
        return {"ok": True, "transfer_ref": capture_ref, "estado": "FUNDS_RELEASED"}

    def reembolsar(self, *, payment_ref, importe=None, idem_key=None, **kw) -> dict:
        """Reembolso real de una CAPTURA ya liberada — `payment_ref` sigue siendo el id de la
        AUTHORIZATION original; hay que resolver primero el id de su CAPTURE. Solo tiene sentido
        ANTES de que se haya enviado el Payout al proveedor (ver docstring del módulo: el estado
        actual del pedido nunca llega a ENTREGADA/FUNDS_RELEASED con un reembolso pendiente)."""
        if not self.configurado():
            return {"ok": False, "mensaje": "PayPal no configurado."}
        try:
            requests = self._req()
            token = self._token()
            if not token:
                return {"ok": False, "mensaje": "PayPal: no se pudo autenticar."}
            ra = requests.get(f"{self._base()}/v2/payments/authorizations/{payment_ref}",
                              headers=self._headers(token), timeout=25)
            if ra.status_code != 200:
                return {"ok": False, "mensaje": f"PayPal {ra.status_code}."}
            capturas = (ra.json().get("links") or [])
            capture_id = next(
                (l.get("href", "").rstrip("/").rsplit("/", 1)[-1]
                 for l in capturas if l.get("rel") == "capture"), None)
            if not capture_id:
                return {"ok": False, "mensaje": "No se encontró ninguna captura asociada."}
            payload = {}
            if importe is not None:
                payload = {"amount": {"value": f"{float(importe):.2f}", "currency_code": "EUR"}}
            rr = requests.post(f"{self._base()}/v2/payments/captures/{capture_id}/refund",
                               json=payload, headers=self._headers(token, idem_key), timeout=25)
            if rr.status_code in (200, 201):
                return {"ok": True, "refund_ref": rr.json().get("id"), "estado": "REFUNDED"}
            return {"ok": False, "mensaje": f"PayPal {rr.status_code}."}
        except Exception as e:
            logger.warning("reembolsar (PayPal): %s", e)
            return {"ok": False, "mensaje": str(e)}

    def cancelar(self, *, payment_ref, idem_key=None, **kw) -> dict:
        """Anula una AUTHORIZATION nunca capturada — `/v2/payments/authorizations/{id}/void`, el
        equivalente exacto de `payment_intents/{id}/cancel` de Stripe (libera la retención sin
        mover fondos, nunca es un reembolso de una captura)."""
        if not self.configurado():
            return {"ok": False, "mensaje": "PayPal no configurado."}
        try:
            requests = self._req()
            token = self._token()
            if not token:
                return {"ok": False, "mensaje": "PayPal: no se pudo autenticar."}
            r = requests.post(f"{self._base()}/v2/payments/authorizations/{payment_ref}/void",
                              headers=self._headers(token, idem_key), timeout=25)
            if r.status_code in (200, 204):
                return {"ok": True, "refund_ref": None, "estado": "REFUNDED"}
            logger.warning("cancelar (PayPal) %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "mensaje": f"PayPal {r.status_code}."}
        except Exception as e:
            logger.warning("cancelar (PayPal): %s", e)
            return {"ok": False, "mensaje": str(e)}
