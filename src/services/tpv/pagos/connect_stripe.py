"""
Pasarela Stripe Connect — marketplace con custodia (F1).

Reutiliza el mismo secret key de Stripe (`api_key`) que el checkout (`stripe.py`) y añade las operaciones de
marketplace vía la API de Connect:
- Cuentas conectadas Express + Account Links (onboarding KYB hospedado).
- Escrow por *destination charge* con `application_fee_amount` y `capture_method=manual` (autoriza/retiene).
- Liberación por captura del PaymentIntent (los fondos van al destino, la comisión a la plataforma).
- Reembolso.
- Idempotencia real por `Idempotency-Key` en cada llamada mutante (evita pagos duplicados en microcortes).

DEGRADABLE: sin `api_key` o sin `requests`, `configurado()` es False y el resolver cae al simulado. Nunca
se inventa un acuse: los estados definitivos los confirma el PSP (directamente o vía webhook en F3).

Config esperada en `pasarela_config` (reutilizada): `api_key`, `modo` (test/live), y opcionalmente `pais`
(ISO-2, por defecto 'ES'), `return_url`, `refresh_url`.
"""

import logging

from src.services.tpv.pagos.base_marketplace import PasarelaMarketplace
from src.services.tpv.pagos.registry import registrar

logger = logging.getLogger("pagos.connect_stripe")

_API = "https://api.stripe.com/v1"


@registrar("stripe_connect", "Stripe Connect (Marketplace)", orden=25)
class PasarelaStripeConnect(PasarelaMarketplace):
    nombre = "stripe_connect"

    def configurado(self) -> bool:
        return bool(self.config.get("api_key"))

    def _auth(self):
        return (self.config["api_key"], "")

    @staticmethod
    def _req():
        import requests  # import perezoso (degradable)
        return requests

    @staticmethod
    def _idem(idem_key):
        return {"Idempotency-Key": idem_key} if idem_key else {}

    # ── Cuentas conectadas / onboarding KYB ──────────────────────────────────
    def crear_cuenta_conectada(self, *, tipo_parte, id_parte, divisa="EUR", email=None,
                               id_empresa=None) -> dict:
        if not self.configurado():
            return {"ok": False, "mensaje": "Stripe Connect no configurado."}
        try:
            requests = self._req()
        except Exception:
            return {"ok": False, "mensaje": "requests no disponible."}
        pais = (self.config.get("pais") or "ES").upper()
        data = {
            "type": "express",
            "country": pais,
            "email": email or "",
            "capabilities[transfers][requested]": "true",
            "capabilities[card_payments][requested]": "true",
            "metadata[tipo_parte]": str(tipo_parte),
            "metadata[id_parte]": str(id_parte),
            "metadata[id_empresa]": str(id_empresa or ""),
        }
        try:
            r = requests.post(f"{_API}/accounts", data=data, auth=self._auth(), timeout=25)
            if r.status_code not in (200, 201):
                logger.warning("Stripe Connect accounts %s: %s", r.status_code, r.text[:200])
                return {"ok": False, "mensaje": f"Stripe respondió {r.status_code}."}
            acct = r.json().get("id")
            link = self.link_onboarding(acct)
            return {"ok": True, "account_id": acct, "onboarding_url": link.get("onboarding_url"),
                    "status": "pending", "psp": "stripe"}
        except Exception as e:
            logger.warning("crear_cuenta_conectada: %s", e)
            return {"ok": False, "mensaje": f"Error Stripe: {e}"}

    def link_onboarding(self, account_id, **kw) -> dict:
        if not self.configurado() or not account_id:
            return {"ok": False, "onboarding_url": None}
        try:
            requests = self._req()
        except Exception:
            return {"ok": False, "onboarding_url": None, "mensaje": "requests no disponible."}
        data = {
            "account": account_id,
            "refresh_url": self.config.get("refresh_url") or "https://smartmanager.local/kyb/refresh",
            "return_url": self.config.get("return_url") or "https://smartmanager.local/kyb/return",
            "type": "account_onboarding",
        }
        try:
            r = requests.post(f"{_API}/account_links", data=data, auth=self._auth(), timeout=25)
            if r.status_code in (200, 201):
                return {"ok": True, "onboarding_url": r.json().get("url")}
            return {"ok": False, "onboarding_url": None, "mensaje": f"Stripe {r.status_code}."}
        except Exception as e:
            logger.warning("link_onboarding: %s", e)
            return {"ok": False, "onboarding_url": None, "mensaje": str(e)}

    def estado_cuenta(self, account_id) -> dict:
        if not self.configurado() or not account_id:
            return {"ok": False, "mensaje": "Stripe Connect no configurado."}
        try:
            requests = self._req()
            r = requests.get(f"{_API}/accounts/{account_id}", auth=self._auth(), timeout=25)
            if r.status_code != 200:
                return {"ok": False, "mensaje": f"Stripe {r.status_code}."}
            j = r.json()
            payouts = bool(j.get("payouts_enabled"))
            charges = bool(j.get("charges_enabled"))
            ext = ((j.get("external_accounts") or {}).get("data") or [])
            banco = ext[0].get("bank_name") if ext else None
            ultimos4 = ext[0].get("last4") if ext else None
            disabled = (j.get("requirements") or {}).get("disabled_reason")
            status = "verified" if payouts else ("restricted" if disabled else "pending")
            return {"ok": True, "status": status, "payouts_enabled": payouts, "charges_enabled": charges,
                    "banco": banco, "ultimos4": ultimos4}
        except Exception as e:
            logger.warning("estado_cuenta: %s", e)
            return {"ok": False, "mensaje": str(e)}

    # ── Escrow / liquidación ─────────────────────────────────────────────────
    def retener_fondos(self, *, importe, divisa="EUR", vendedor_account, comision=0, referencia=None,
                       idem_key=None, id_empresa=None, **kw) -> dict:
        if not self.configurado():
            return {"ok": False, "mensaje": "Stripe Connect no configurado."}
        if not vendedor_account:
            return {"ok": False, "mensaje": "Falta la cuenta conectada del vendedor."}
        try:
            requests = self._req()
        except Exception:
            return {"ok": False, "mensaje": "requests no disponible."}
        amount = int(round(float(importe) * 100))
        fee = int(round(float(comision or 0) * 100))
        data = {
            "amount": str(amount),
            "currency": (divisa or "EUR").lower(),
            "capture_method": "manual",                       # escrow: autoriza y retiene
            "transfer_data[destination]": vendedor_account,   # destination charge → al vendedor
        }
        if fee:
            data["application_fee_amount"] = str(fee)          # comisión de la plataforma
        if referencia:
            data["metadata[referencia]"] = str(referencia)
        try:
            r = requests.post(f"{_API}/payment_intents", data=data, headers=self._idem(idem_key),
                              auth=self._auth(), timeout=25)
            if r.status_code in (200, 201):
                j = r.json()
                return {"ok": True, "payment_ref": j.get("id"), "client_secret": j.get("client_secret"),
                        "estado": "PAYMENT_PENDING"}
            logger.warning("retener_fondos %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "mensaje": f"Stripe {r.status_code}."}
        except Exception as e:
            logger.warning("retener_fondos: %s", e)
            return {"ok": False, "mensaje": str(e)}

    def liberar_fondos(self, *, payment_ref, idem_key=None, **kw) -> dict:
        if not self.configurado():
            return {"ok": False, "mensaje": "Stripe Connect no configurado."}
        if not payment_ref:
            return {"ok": False, "mensaje": "Falta la referencia de pago."}
        try:
            requests = self._req()
            r = requests.post(f"{_API}/payment_intents/{payment_ref}/capture", headers=self._idem(idem_key),
                              auth=self._auth(), timeout=25)
            if r.status_code == 200:
                return {"ok": True, "transfer_ref": payment_ref, "estado": "FUNDS_RELEASED"}
            logger.warning("liberar_fondos %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "mensaje": f"Stripe {r.status_code}."}
        except Exception as e:
            logger.warning("liberar_fondos: %s", e)
            return {"ok": False, "mensaje": str(e)}

    def reembolsar(self, *, payment_ref, importe=None, idem_key=None, **kw) -> dict:
        if not self.configurado():
            return {"ok": False, "mensaje": "Stripe Connect no configurado."}
        try:
            requests = self._req()
            data = {"payment_intent": payment_ref}
            if importe is not None:
                data["amount"] = str(int(round(float(importe) * 100)))
            r = requests.post(f"{_API}/refunds", data=data, headers=self._idem(idem_key),
                              auth=self._auth(), timeout=25)
            if r.status_code in (200, 201):
                return {"ok": True, "refund_ref": r.json().get("id"), "estado": "REFUNDED"}
            return {"ok": False, "mensaje": f"Stripe {r.status_code}."}
        except Exception as e:
            logger.warning("reembolsar: %s", e)
            return {"ok": False, "mensaje": str(e)}
