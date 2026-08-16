"""
Interfaz de pasarela con capacidades de MARKETPLACE (F1 — Marketplace + Pagos).

Extiende `PasarelaPago` (cobro simple de TPV/web) con las operaciones propias de un marketplace con
custodia de fondos de terceros: cuentas conectadas + onboarding KYB, retención (escrow), liberación con
split de comisión, reembolso y (opcional) IBAN virtual. La implementación concreta la aporta cada PSP
regulado (Stripe Connect); el fallback `simulado` permite desarrollar/probar sin credenciales SIN fingir
estados reales.

Contratos de retorno (todos degradables, nunca lanzan): dicts con `ok` + campos específicos. Los importes
se pasan en unidad mayor (euros), cada adaptador convierte a la unidad mínima del PSP.
"""

import logging

from src.services.tpv.pagos.base import PasarelaPago

logger = logging.getLogger("pagos.base_marketplace")


class PasarelaMarketplace(PasarelaPago):
    """Contrato de un PSP con capacidades de marketplace (cuentas conectadas + escrow + payouts)."""

    #: marca de capacidad (permite detectar el adaptador sin depender del nombre)
    capacidad_marketplace = True

    def modo(self) -> str:
        """'live' | 'test' | 'simulado' — origen honesto para la UI/auditoría."""
        if not self.configurado():
            return "simulado"
        return "test" if self.es_test() else "live"

    # ── Cuentas conectadas / onboarding KYB ──────────────────────────────────
    def crear_cuenta_conectada(self, *, tipo_parte, id_parte, divisa="EUR", email=None,
                               id_empresa=None) -> dict:
        """Provisiona una cuenta conectada en el PSP. Devuelve
        {ok, account_id, onboarding_url, status, psp}."""
        return {"ok": False, "mensaje": "Cuentas conectadas no soportadas por esta pasarela."}

    def link_onboarding(self, account_id, **kw) -> dict:
        """(Re)genera el enlace de onboarding hospedado (KYB). Devuelve {ok, onboarding_url}."""
        return {"ok": False, "onboarding_url": None,
                "mensaje": "Onboarding no soportado por esta pasarela."}

    def estado_cuenta(self, account_id) -> dict:
        """Estado KYB + metadatos: {ok, status, payouts_enabled, charges_enabled, banco, ultimos4}."""
        return {"ok": False, "mensaje": "Estado de cuenta no soportado."}

    # ── Escrow / liquidación ─────────────────────────────────────────────────
    def retener_fondos(self, *, importe, divisa="EUR", vendedor_account, comision=0, referencia=None,
                       idem_key=None, id_empresa=None, **kw) -> dict:
        """Autoriza y retiene (escrow) el importe con destino al vendedor y `comision` para la plataforma.
        Devuelve {ok, payment_ref, estado, client_secret?}."""
        return {"ok": False, "mensaje": "Retención de fondos no soportada."}

    def liberar_fondos(self, *, payment_ref, idem_key=None, **kw) -> dict:
        """Libera los fondos retenidos al vendedor (y cobra la comisión). Devuelve {ok, transfer_ref, estado}."""
        return {"ok": False, "mensaje": "Liberación de fondos no soportada."}

    def reembolsar(self, *, payment_ref, importe=None, idem_key=None, **kw) -> dict:
        """Reembolsa (total o parcial) una retención/cobro. Devuelve {ok, refund_ref, estado}."""
        return {"ok": False, "mensaje": "Reembolso no soportado."}

    def crear_iban_virtual(self, *, account_id=None, referencia=None, **kw) -> dict:
        """IBAN virtual único por operación/comprador para conciliación de transferencias entrantes."""
        return {"ok": False, "mensaje": "IBAN virtual no soportado."}
