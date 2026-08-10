"""
Marketplace · Integraciones Comerciales · **Conector Shopify** (Fase WEB-16) — segunda integración comercial
real, siguiendo EXACTAMENTE el patrón de WooCommerce (WEB-15). Toda la lógica específica de Shopify vive SOLO
aquí (`shopify/`): nunca en el motor, ni en Marketplace, ni en el Canal Web.

Reutiliza el motor WEB-13 (contratos/capacidades/estados/errores/costuras), el SecretManager y los MOTORES del
ERP (catálogo/clientes/pedidos/stock). Multiempresa/multitienda. Degradable: `disponible()` = True solo con
Shop URL + Access Token reales (SecretManager); sin ellos → `MISSING_CREDENTIALS`, sin red. Sin webhooks/OAuth
completo/polling/jobs/colas remotas (preparado con las costuras del motor, no activado).
"""

from src.services.marketplace.integraciones_comerciales.shopify import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.shopify.adaptador import \
    ShopifyAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.shopify.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector Shopify en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("shopify", ShopifyAdapter)
