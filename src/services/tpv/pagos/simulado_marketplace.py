"""
Pasarela de marketplace SIMULADA (fallback degradable, F1).

Permite construir y probar todo el flujo (onboarding → escrow → liberación → reembolso) SIN credenciales de
un PSP real. Es honesta: una cuenta simulada queda en estado `pending` (nunca `verified` como si un KYB real
la hubiera aprobado) y las referencias llevan prefijos `_sim_` inequívocos. En producción real la sustituye
Stripe Connect (`connect_stripe.py`) en cuanto hay credenciales.
"""

import logging
import uuid

from src.services.tpv.pagos.base_marketplace import PasarelaMarketplace
from src.services.tpv.pagos.registry import registrar

logger = logging.getLogger("pagos.simulado_marketplace")


@registrar("simulado_mkt", "Simulado (Marketplace)", orden=999)
class PasarelaMarketplaceSimulada(PasarelaMarketplace):
    nombre = "simulado_mkt"

    def configurado(self) -> bool:
        # Siempre "configurada" para poder operar en desarrollo, pero su modo es 'simulado'.
        return True

    def modo(self) -> str:
        return "simulado"

    def crear_cuenta_conectada(self, *, tipo_parte, id_parte, divisa="EUR", email=None,
                               id_empresa=None) -> dict:
        return {"ok": True, "account_id": f"acct_sim_{uuid.uuid4().hex[:16]}", "onboarding_url": None,
                "status": "pending", "psp": "simulado"}

    def link_onboarding(self, account_id, **kw) -> dict:
        return {"ok": True, "onboarding_url": None,
                "mensaje": "Modo simulado: no hay onboarding hospedado real."}

    def estado_cuenta(self, account_id) -> dict:
        # No inventa una validación KYB que no ha ocurrido.
        return {"ok": True, "status": "pending", "payouts_enabled": False, "charges_enabled": False,
                "banco": None, "ultimos4": None}

    def retener_fondos(self, *, importe, divisa="EUR", vendedor_account=None, comision=0, referencia=None,
                       idem_key=None, id_empresa=None, **kw) -> dict:
        ref = idem_key or referencia or uuid.uuid4().hex[:16]
        return {"ok": True, "payment_ref": f"pi_sim_{ref}", "estado": "FUNDS_HELD", "modo": "simulado",
                "comision": float(comision or 0)}

    def liberar_fondos(self, *, payment_ref, idem_key=None, **kw) -> dict:
        return {"ok": True, "transfer_ref": f"tr_sim_{payment_ref}", "estado": "FUNDS_RELEASED",
                "modo": "simulado"}

    def reembolsar(self, *, payment_ref, importe=None, idem_key=None, **kw) -> dict:
        return {"ok": True, "refund_ref": f"re_sim_{payment_ref}", "estado": "REFUNDED", "modo": "simulado"}
