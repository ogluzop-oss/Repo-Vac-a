"""
Marketplace · Integraciones Comerciales · **Conector Amazon** (Fase WEB-20) — primer MARKETPLACE (canal de
venta externo). Replica EXACTAMENTE el patrón de los ecommerce (WooCommerce/Shopify/PrestaShop/Magento/
OpenCart). Toda la lógica específica de Amazon vive SOLO aquí (`amazon/`).

RESPONSABILIDAD (marketplace): sincroniza productos/pedidos/clientes/stock/precios/estados. **NO** crea webs,
dominios, SSL ni tiendas (sus capacidades en el motor ya lo reflejan). Reutiliza el motor WEB-13, el
SecretManager y los MOTORES del ERP. Degradable: `disponible()` = True solo con host SP-API + Access Token
reales; sin ellos → `MISSING_CREDENTIALS`, sin red. Aparece automáticamente en el Centro (WEB-16.5).

Nota de honestidad: la Amazon SP-API real requiere además LWA (OAuth) + firma AWS SigV4; esta estructura queda
operativa-ready y degradable (bloqueo externo de credenciales/partner), sin falsear conexiones.
"""

from src.services.marketplace.integraciones_comerciales.amazon import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.amazon.adaptador import \
    AmazonAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.amazon.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector Amazon en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("amazon", AmazonAdapter)
