"""Selección del adaptador de e-commerce según la config de la empresa."""

import logging

from src.services.tpv.ecommerce.prestashop import AdaptadorPrestaShop
from src.services.tpv.ecommerce.shopify import AdaptadorShopify
from src.services.tpv.ecommerce.web import AdaptadorWeb
from src.services.tpv.ecommerce.woocommerce import AdaptadorWooCommerce

logger = logging.getLogger("ecommerce.factory")

_ADAPTADORES = {
    "web": AdaptadorWeb,
    "woocommerce": AdaptadorWooCommerce,
    "shopify": AdaptadorShopify,
    "prestashop": AdaptadorPrestaShop,
}


def adaptador_para(config: dict):
    """Adaptador para una config dada (cae a 'web' si la plataforma no se reconoce)."""
    clase = _ADAPTADORES.get((config or {}).get("plataforma", "web"), AdaptadorWeb)
    return clase(config)


def adaptador_actual():
    """Adaptador de la plataforma configurada para la empresa activa."""
    try:
        from src.db import ecommerce as ecom_db
        return adaptador_para(ecom_db.obtener_config())
    except Exception as e:
        logger.error("adaptador_actual: %s", e)
        return AdaptadorWeb({})
