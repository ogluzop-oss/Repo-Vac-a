"""
Marketplace · Integraciones Comerciales · **Conector Magento** (Fase WEB-18) — replica EXACTAMENTE el patrón
de WooCommerce/Shopify/PrestaShop. Toda la lógica específica de Magento vive SOLO aquí (`magento/`): nunca en
el motor, ni en el Centro, ni en los conectores existentes.

Reutiliza el motor WEB-13 (contratos/capacidades/estados/errores/colas/pipeline), el SecretManager y los
MOTORES del ERP (catálogo/clientes/pedidos/stock). Multiempresa/multitienda. Degradable: `disponible()` = True
solo con Shop URL + Access Token reales (SecretManager); sin ellos → `MISSING_CREDENTIALS`, sin red. Aparece
automáticamente en el Centro de Integraciones (WEB-16.5) al estar registrado en el motor.
"""

from src.services.marketplace.integraciones_comerciales.magento import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.magento.adaptador import \
    MagentoAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.magento.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector Magento en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("magento", MagentoAdapter)
