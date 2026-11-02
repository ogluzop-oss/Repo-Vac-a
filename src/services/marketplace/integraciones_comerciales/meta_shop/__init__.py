"""
Marketplace · Integraciones Comerciales · **Conector Meta Shop** (Instagram Shopping + Facebook
Shop). Cierra una brecha real confirmada por auditoría (ver `adaptador.py`): replica EXACTAMENTE
el patrón consolidado (Amazon/eBay/Miravia/AliExpress/TikTok Shop). Toda la lógica específica vive
SOLO aquí (`meta_shop/`).

RESPONSABILIDAD (marketplace): sincroniza catálogo/stock/precios/pedidos contra el Catálogo de
Comercio de Meta (Commerce Manager). **NO** crea webs, dominios, SSL ni tiendas (eso es de
Hostinger/Canal Web), y **NO** es lo mismo que la mensajería/bandeja social de
`services.redes_sociales` (dominio distinto: aquí es catálogo de producto, allí es conversación).
Reutiliza el motor WEB-13, el SecretManager y los MOTORES del ERP. Degradable: `disponible()` =
True solo con Access Token + Catalog ID reales; sin ellos → `MISSING_CREDENTIALS`, sin red.
Aparece automáticamente en el Centro (WEB-16.5).
"""

from src.services.marketplace.integraciones_comerciales.meta_shop import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.meta_shop.adaptador import (  # noqa: F401
    FacebookShopAdapter, InstagramShoppingAdapter)
from src.services.marketplace.integraciones_comerciales.meta_shop.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra los dos conectores Meta Shop en el motor (punto de extensión público de WEB-13).
    Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("instagram_shopping", InstagramShoppingAdapter)
    registrar_adaptador("facebook_shop", FacebookShopAdapter)
