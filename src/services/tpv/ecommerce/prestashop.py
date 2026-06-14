"""Adaptador PrestaShop (Webservice API).

base_url = https://mitienda.com ; api_key = clave del Webservice (auth básica,
usuario=api_key, contraseña vacía). El alta de un pedido completo en PrestaShop
exige el flujo carrito→cliente→direcciones→pedido (XML); aquí se valida la
conexión y se deja el pedido registrado localmente con su referencia. La compra
se completa en la web (botón "Ir a la Web"). Degrada con elegancia.
"""

import logging

from src.services.tpv.ecommerce.base import AdaptadorEcommerce

logger = logging.getLogger("ecommerce.presta")


class AdaptadorPrestaShop(AdaptadorEcommerce):
    nombre = "prestashop"

    def configurado(self) -> bool:
        return bool(self.url_web() and self.config.get("api_key"))

    def crear_pedido(self, pedido: dict) -> str | None:
        if not self.configurado():
            return None
        try:
            import requests
        except Exception:
            return None
        base = self.url_web().rstrip("/")
        try:
            # Comprueba el acceso al Webservice (auth básica: api_key:'').
            resp = requests.get(f"{base}/api/", auth=(self.config["api_key"], ""), timeout=15)
            if resp.status_code not in (200, 401):
                logger.warning("PrestaShop /api respondió %s", resp.status_code)
        except Exception as e:
            logger.warning("PrestaShop sin conexión: %s", e)
        # El pedido completo (carrito+cliente+direcciones) se cierra en la web.
        logger.info("PrestaShop: pedido %s registrado localmente; completar en la web.",
                    pedido.get("id_pedido"))
        return None
