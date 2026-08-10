"""
Motor · ADAPTADORES de conector (Fase WEB-13). Cada plataforma tiene un adaptador PREPARADO (vacío): declara
sus capacidades y versión, y hereda los contratos (`NotImplementedError`). **Sin conexión, sin API, sin
autenticación.** Añadir una plataforma futura = registrar su adaptador, sin tocar el motor (ramificar por plataforma está
prohibido). Las fases WEB-14/15/16 implementarán estos adaptadores.
"""

from src.services.marketplace.integraciones_comerciales.conector import \
    ConectorPreparado
from src.services.marketplace.integraciones_comerciales.motor.capacidades import \
    capacidades
from src.services.marketplace.integraciones_comerciales.motor.pipeline import \
    PipelineSincronizacion
from src.services.marketplace.integraciones_comerciales.motor.validacion import \
    Validador
from src.services.marketplace.integraciones_comerciales.motor.versiones import \
    VersionInfo


class AdaptadorConector(ConectorPreparado):
    """Base de todos los adaptadores. Une conector (contratos), capacidades, versión, validador y pipeline.
    `disponible()` = False (nada conectado). Genérico si se instancia con una plataforma no registrada."""

    plataforma = "base"
    version = VersionInfo()

    def __init__(self, plataforma=None):
        super().__init__((plataforma or type(self).plataforma or "base").lower())

    def capacidades(self):
        return capacidades(self.plataforma)

    def validador(self) -> Validador:
        return Validador(self.plataforma)

    def pipeline(self) -> PipelineSincronizacion:
        return PipelineSincronizacion(self.plataforma)

    def descriptor(self) -> dict:
        return {"plataforma": self.plataforma, "disponible": self.disponible(), "estado": "PREPARADO",
                "capacidades": self.capacidades().soportadas(), "version": type(self).version.as_dict()}


# ── Hostinger: proveedor de CREACIÓN web con IA (preparado, sin conectar) ─────
class HostingerAdapter(AdaptadorConector):
    """Adaptador Hostinger: creación IA + dominio + SSL + publicación + info + conexión automática posterior
    con Smart Manager. TODO preparado; ninguna API/autenticación."""
    plataforma = "hostinger"
    version = VersionInfo(api_version="1.0", connector_version="0.1.0", minimum_version="1.0")

    def crear_web_ia(self, especificacion) -> dict:
        raise NotImplementedError("Hostinger: creación IA preparada (sin conexión real)")

    def publicar(self) -> dict:
        raise NotImplementedError("Hostinger: publicación preparada")

    def configurar_dominio(self, dominio) -> dict:
        raise NotImplementedError("Hostinger: dominio preparado")

    def configurar_ssl(self) -> dict:
        raise NotImplementedError("Hostinger: SSL preparado")

    def info_web(self) -> dict:
        raise NotImplementedError("Hostinger: información de la web preparada")

    def conectar_smart_manager(self, *, id_empresa=None) -> dict:
        """Vinculación automática posterior (Empresa→Dominio→Canal Web→Catálogo→…→Stock). Preparada."""
        raise NotImplementedError("Hostinger: conexión automática con Smart Manager preparada")


# ── Conectores ecommerce / marketplace (preparados, vacíos) ───────────────────
class WooCommerceConnector(AdaptadorConector):
    plataforma = "woocommerce"
    version = VersionInfo(api_version="wc/v3", connector_version="0.1.0", minimum_version="3.5")


class ShopifyConnector(AdaptadorConector):
    plataforma = "shopify"
    version = VersionInfo(api_version="2024-01", connector_version="0.1.0", minimum_version="2023-01")


class PrestaShopConnector(AdaptadorConector):
    plataforma = "prestashop"
    version = VersionInfo(api_version="1.7", connector_version="0.1.0", minimum_version="1.6")


class MagentoConnector(AdaptadorConector):
    plataforma = "magento"
    version = VersionInfo(api_version="V1", connector_version="0.1.0", minimum_version="2.3")


class OpenCartConnector(AdaptadorConector):
    plataforma = "opencart"
    version = VersionInfo(api_version="3.0", connector_version="0.1.0", minimum_version="3.0")


class AmazonConnector(AdaptadorConector):
    plataforma = "amazon"
    version = VersionInfo(api_version="SP-API", connector_version="0.1.0", minimum_version="1.0")


class EbayConnector(AdaptadorConector):
    plataforma = "ebay"
    version = VersionInfo(api_version="Sell v1", connector_version="0.1.0", minimum_version="1.0")


class MiraviaConnector(AdaptadorConector):
    plataforma = "miravia"
    version = VersionInfo(api_version="1.0", connector_version="0.1.0", minimum_version="1.0")


class AliExpressConnector(AdaptadorConector):
    plataforma = "aliexpress"
    version = VersionInfo(api_version="1.0", connector_version="0.1.0", minimum_version="1.0")


class TikTokShopConnector(AdaptadorConector):
    plataforma = "tiktok_shop"
    version = VersionInfo(api_version="202309", connector_version="0.1.0", minimum_version="1.0")


# Registro plataforma → adaptador (extensible; el motor nunca ramifica por plataforma).
ADAPTADORES = {
    "hostinger": HostingerAdapter,
    "woocommerce": WooCommerceConnector,
    "shopify": ShopifyConnector,
    "prestashop": PrestaShopConnector,
    "magento": MagentoConnector,
    "opencart": OpenCartConnector,
    "amazon": AmazonConnector,
    "ebay": EbayConnector,
    "miravia": MiraviaConnector,
    "aliexpress": AliExpressConnector,
    "tiktok_shop": TikTokShopConnector,
}


def adaptador(plataforma) -> AdaptadorConector:
    """Adaptador PREPARADO de una plataforma (por registro; genérico si no está registrada)."""
    cls = ADAPTADORES.get((plataforma or "").lower())
    return cls() if cls else AdaptadorConector(plataforma)


def registrar_adaptador(plataforma: str, cls) -> None:
    ADAPTADORES[(plataforma or "").lower()] = cls
