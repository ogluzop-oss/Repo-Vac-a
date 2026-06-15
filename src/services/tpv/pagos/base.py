"""Interfaz común de las pasarelas de pago."""

import logging

logger = logging.getLogger("pagos.base")


class PasarelaPago:
    """Contrato que cumplen todas las pasarelas (Stripe/PayPal/Redsys/simulado)."""

    nombre = "base"

    def __init__(self, config: dict):
        self.config = config or {}

    def configurado(self) -> bool:
        """True si hay credenciales suficientes para cobrar."""
        return False

    def moneda(self) -> str:
        return (self.config.get("moneda") or "EUR").upper()

    def es_test(self) -> bool:
        return (self.config.get("modo") or "test").lower() != "live"

    def crear_cobro(self, pedido: dict) -> dict:
        """Inicia un cobro para el pedido. Devuelve
        {ok, url, referencia, estado, mensaje}. ``url`` es el enlace de pago que
        usa el cliente; ``referencia`` identifica el cobro en la pasarela."""
        return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                "mensaje": "Pasarela no configurada."}

    def verificar_pago(self, referencia: str) -> str:
        """Estado del cobro: 'pendiente' | 'pagado' | 'fallido'."""
        return "pendiente"
