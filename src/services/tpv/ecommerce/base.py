"""Interfaz común de los adaptadores de e-commerce."""

import logging

logger = logging.getLogger("ecommerce.adapter")


class AdaptadorEcommerce:
    """Contrato que cumplen todos los adaptadores de plataforma."""

    nombre = "base"

    def __init__(self, config: dict):
        self.config = config or {}

    # URL de la tienda online (para el botón "Ir a la Web").
    def url_web(self) -> str:
        return (self.config.get("base_url") or "").strip()

    def configurado(self) -> bool:
        """True si hay datos suficientes para operar con la plataforma."""
        return bool(self.url_web())

    # Crea/sincroniza el pedido en la plataforma. Devuelve la referencia externa
    # (id/nº de pedido) o None si no se pudo (sin creds, sin red, plataforma 'web').
    def crear_pedido(self, pedido: dict) -> str | None:
        return None

    # Trae pedidos remotos (para sincronizar). Por defecto, ninguno.
    def listar_pedidos_remotos(self) -> list:
        return []
