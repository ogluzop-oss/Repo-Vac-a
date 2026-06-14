"""Adaptador de WEB PROPIA / genérica: solo enlaza a la URL configurada.

No sincroniza por API (la web propia puede no exponer una). El pedido queda
registrado localmente y el trabajador completa la compra en la web mediante el
botón "Ir a la Web". Es el modo por defecto y sin dependencias externas.
"""

from src.services.tpv.ecommerce.base import AdaptadorEcommerce


class AdaptadorWeb(AdaptadorEcommerce):
    nombre = "web"

    def crear_pedido(self, pedido: dict) -> str | None:
        # Sin API: el pedido vive en local; la compra se cierra en la web.
        return None
