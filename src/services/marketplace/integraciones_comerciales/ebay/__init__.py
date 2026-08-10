"""
Marketplace · Integraciones Comerciales · **Conector eBay** (Fase WEB-21) — MARKETPLACE (canal de venta
externo). Replica EXACTAMENTE el patrón consolidado (Amazon + ecommerce). Toda la lógica específica de eBay
vive SOLO aquí (`ebay/`).

RESPONSABILIDAD (marketplace): sincroniza productos/pedidos/clientes/stock/precios/estados. **NO** crea webs,
dominios, SSL ni tiendas. Reutiliza el motor WEB-13, el SecretManager y los MOTORES del ERP. Degradable:
`disponible()` = True solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red. Aparece
automáticamente en el Centro (WEB-16.5).

Honestidad: las eBay Sell APIs usan OAuth2 (token de usuario) + scopes; esta estructura queda operativa-ready
y degradable (bloqueo externo de credenciales/OAuth), sin falsear conexiones.
"""

from src.services.marketplace.integraciones_comerciales.ebay import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.ebay.adaptador import \
    EbayAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.ebay.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector eBay en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("ebay", EbayAdapter)
