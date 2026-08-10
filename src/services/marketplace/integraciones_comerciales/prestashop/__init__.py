"""
Marketplace · Integraciones Comerciales · **Conector PrestaShop** (Fase WEB-17) — replica EXACTAMENTE el
patrón de WooCommerce (WEB-15) y Shopify (WEB-16). Toda la lógica específica de PrestaShop vive SOLO aquí
(`prestashop/`): nunca en el motor, ni en el Centro, ni en los conectores existentes.

Reutiliza el motor WEB-13 (contratos/capacidades/estados/errores/costuras), el SecretManager y los MOTORES del
ERP (catálogo/clientes/pedidos/stock). Multiempresa/multitienda. Degradable: `disponible()` = True solo con
Shop URL + API Key reales (SecretManager); sin ellos → `MISSING_CREDENTIALS`, sin red. Aparece automáticamente
en el Centro de Integraciones (WEB-16.5) al estar registrado en el motor.
"""

from src.services.marketplace.integraciones_comerciales.prestashop import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.prestashop.adaptador import \
    PrestaShopAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.prestashop.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector PrestaShop en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("prestashop", PrestaShopAdapter)
