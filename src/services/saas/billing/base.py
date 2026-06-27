"""
BillingProvider — interfaz desacoplada de cobro de suscripciones (FASE SAAS-E).

Cada proveedor (Stripe/PayPal/Redsys) implementa `cobrar`. Sin dependencias obligatorias: si el
SDK del proveedor no está disponible o no hay credenciales, el proveedor devuelve un resultado
controlado (no rompe). El proveedor por defecto es 'simulado' (útil para pruebas/onboarding).
"""

import logging
import uuid

logger = logging.getLogger("saas.billing")


class BillingProvider:
    codigo = "base"

    def cobrar(self, importe, *, referencia=None, datos=None) -> dict:
        raise NotImplementedError

    def _ref(self):
        return f"{self.codigo}_{uuid.uuid4().hex[:16]}"


class SimuladoProvider(BillingProvider):
    codigo = "simulado"

    def cobrar(self, importe, *, referencia=None, datos=None) -> dict:
        return {"ok": True, "estado": "pagado", "ref_externa": self._ref(), "proveedor": self.codigo}


class StripeProvider(BillingProvider):
    codigo = "stripe"

    def cobrar(self, importe, *, referencia=None, datos=None) -> dict:
        try:
            import stripe  # noqa: F401  (solo si está instalado y configurado)
        except Exception:
            return {"ok": False, "estado": "no_configurado", "proveedor": self.codigo}
        # Integración real requiere credenciales/cliente; se deja preparado el punto de extensión.
        return {"ok": False, "estado": "no_implementado", "proveedor": self.codigo}


class PaypalProvider(BillingProvider):
    codigo = "paypal"

    def cobrar(self, importe, *, referencia=None, datos=None) -> dict:
        return {"ok": False, "estado": "no_configurado", "proveedor": self.codigo}


class RedsysProvider(BillingProvider):
    codigo = "redsys"

    def cobrar(self, importe, *, referencia=None, datos=None) -> dict:
        return {"ok": False, "estado": "no_configurado", "proveedor": self.codigo}


_PROVEEDORES = {p.codigo: p for p in (SimuladoProvider, StripeProvider, PaypalProvider, RedsysProvider)}


def proveedor(codigo=None) -> BillingProvider:
    """Factory: devuelve el proveedor por código (defecto 'simulado')."""
    return _PROVEEDORES.get((codigo or "simulado").lower(), SimuladoProvider)()
