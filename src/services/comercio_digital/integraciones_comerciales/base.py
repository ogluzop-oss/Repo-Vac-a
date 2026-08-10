"""
Integraciones Comerciales (Fase WEB-02) — CONTRATO abstracto de un conector con una plataforma EXTERNA
(WooCommerce/Shopify/Prestashop/Magento/OpenCart/Amazon/eBay/Miravia/AliExpress/TikTok Shop, …). Es la
arquitectura que **Marketplace** asumirá ("Integraciones Comerciales"); el Canal Web SÓLO redirige aquí.

En esta fase SÓLO se define el contrato: NO se implementa ninguna integración real (ni API, ni OAuth, ni sync).
La persistencia de configuración de plataforma externa reutilizará la existente (`db/ecommerce.py`,
`ecommerce_config`, Escenario A) cuando se implemente — aquí no se toca ni se conecta.
"""


class ConectorComercial:
    """Interfaz de un conector con una plataforma de venta externa. Implementaciones DEGRADABLES: sin
    credenciales/servicio → `disponible()` = False. Nunca guardan secretos en claro (Secret Manager)."""

    clave = "base"
    nombre = "Conector base"

    def disponible(self) -> bool:
        return False

    def conectar(self, config: dict) -> dict:
        """Establece/valida la conexión con la plataforma (PREPARADO)."""
        raise NotImplementedError

    def sincronizar(self, *, id_empresa=None) -> dict:
        """Sincroniza catálogo/pedidos/stock con la plataforma (PREPARADO)."""
        raise NotImplementedError

    def descriptor(self) -> dict:
        return {"clave": self.clave, "nombre": self.nombre, "disponible": self.disponible()}
