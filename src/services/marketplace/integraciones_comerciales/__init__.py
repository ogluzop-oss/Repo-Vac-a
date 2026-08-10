"""
Marketplace · **Integraciones Comerciales** (Fase WEB-03). Submódulo INDEPENDIENTE de Marketplace, separado de
las "Extensiones Smart Manager" (plugins, que NO se tocan). Centraliza la conexión con plataformas ecommerce
externas (WooCommerce/Shopify/Prestashop/Magento/OpenCart/Amazon/eBay/Miravia/AliExpress/TikTok Shop).

Responsabilidad (SOLO): conectar/desconectar plataformas, validar credenciales, sincronizar productos/pedidos/
clientes/stock/precios/estados. **NO** publica/crea webs ni gestiona dominios/Hostinger (eso es del Canal Web).

Estado actual: **arquitectura PREPARADA, sin conexiones reales** (ni API, ni OAuth). El Canal Web (Escenario B)
redirige aquí; la ejecución real de cada conector se implementará en fases posteriores. Reutiliza el catálogo
de plataformas de `comercio_digital.integraciones_comerciales` (N7, sin duplicar).
"""

from src.services.comercio_digital.integraciones_comerciales import \
    catalogo as plataformas_catalogo
from src.services.marketplace.integraciones_comerciales import (conector,  # noqa: F401
                                                                contratos,
                                                                estados,
                                                                motor,
                                                                servicio)
from src.services.marketplace.integraciones_comerciales.motor import (  # noqa: F401
    ConnectorCapabilities, adaptador, capacidades)
from src.services.marketplace.integraciones_comerciales import \
    hostinger  # noqa: F401  (registra el adaptador Hostinger real vía el punto de extensión del motor)
from src.services.marketplace.integraciones_comerciales import \
    woocommerce  # noqa: F401  (registra el conector WooCommerce real)
from src.services.marketplace.integraciones_comerciales import \
    shopify  # noqa: F401  (registra el conector Shopify real)
from src.services.marketplace.integraciones_comerciales import \
    prestashop  # noqa: F401  (registra el conector PrestaShop real)
from src.services.marketplace.integraciones_comerciales import \
    magento  # noqa: F401  (registra el conector Magento real)
from src.services.marketplace.integraciones_comerciales import \
    opencart  # noqa: F401  (registra el conector OpenCart real)
from src.services.marketplace.integraciones_comerciales import \
    amazon  # noqa: F401  (registra el conector Amazon real — marketplace)
from src.services.marketplace.integraciones_comerciales import \
    ebay  # noqa: F401  (registra el conector eBay real — marketplace)
from src.services.marketplace.integraciones_comerciales import \
    miravia  # noqa: F401  (registra el conector Miravia real — marketplace)
from src.services.marketplace.integraciones_comerciales import \
    aliexpress  # noqa: F401  (registra el conector AliExpress real — marketplace)
from src.services.marketplace.integraciones_comerciales import \
    tiktok_shop  # noqa: F401  (registra el conector TikTok Shop real — marketplace)
from src.services.marketplace.integraciones_comerciales import \
    web_generica  # noqa: F401  (registra la web tradicional: feed + REST — web_tradicional)

hostinger.registrar()
woocommerce.registrar()
shopify.registrar()
prestashop.registrar()
magento.registrar()
opencart.registrar()
amazon.registrar()
ebay.registrar()
miravia.registrar()
aliexpress.registrar()
tiktok_shop.registrar()
web_generica.registrar()
from src.services.marketplace.integraciones_comerciales.conector import (  # noqa: F401
    ConectorPreparado, conector as obtener_conector)
from src.services.marketplace.integraciones_comerciales.servicio import (  # noqa: F401
    AMBITOS_SYNC, crear_integracion, deshabilitar, editar_integracion,
    eliminar_integracion, estado_integraciones, habilitar, listar, obtener,
    sincronizar, validar)

APARTADO = "integraciones_comerciales"
ESTADO = "PREPARADO"


def listar_plataformas(tipo=None) -> list:
    return plataformas_catalogo.listar(tipo)


def descriptor() -> dict:
    return {"apartado": APARTADO, "estado": ESTADO, "propietario": "marketplace",
            "responsabilidades": ["conectar", "desconectar", "validar_credenciales",
                                  "sincronizar_productos", "sincronizar_pedidos", "sincronizar_clientes",
                                  "sincronizar_stock", "sincronizar_precios", "sincronizar_estados"],
            "no_responsabilidades": ["publicar_web", "crear_web", "dominios", "hostinger"],
            "estados": list(estados.ESTADOS), "plataformas": plataformas_catalogo.listar()}


__all__ = ["APARTADO", "ESTADO", "estados", "contratos", "conector", "servicio",
           "ConectorPreparado", "obtener_conector", "listar_plataformas", "descriptor",
           "crear_integracion", "editar_integracion", "eliminar_integracion", "habilitar",
           "deshabilitar", "listar", "obtener", "estado_integraciones",
           "validar", "sincronizar", "AMBITOS_SYNC",
           "motor", "capacidades", "adaptador", "ConnectorCapabilities", "hostinger", "woocommerce",
           "shopify", "prestashop", "magento", "opencart", "amazon", "ebay", "miravia", "aliexpress",
           "tiktok_shop"]
