"""
Marketplace · Integraciones Comerciales · **Conector AliExpress** (Fase WEB-23) — MARKETPLACE (canal de venta
externo). Replica EXACTAMENTE el patrón consolidado (Amazon/eBay/Miravia + ecommerce). Toda la lógica
específica de AliExpress vive SOLO aquí (`aliexpress/`).

RESPONSABILIDAD (marketplace): sincroniza productos/pedidos/clientes/stock/precios/estados. **NO** crea webs,
dominios, SSL ni tiendas (eso es de Hostinger). Reutiliza el motor WEB-13, el SecretManager y los MOTORES del
ERP. Degradable: `disponible()` = True solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red.
Aparece automáticamente en el Centro (WEB-16.5).

Honestidad: la Alibaba Open Platform (TOP) usa app_key/app_secret + firma/sesión; esta estructura queda
operativa-ready y degradable (bloqueo externo de credenciales), sin falsear conexiones.
"""

from src.services.marketplace.integraciones_comerciales.aliexpress import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.aliexpress.adaptador import \
    AliExpressAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.aliexpress.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector AliExpress en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("aliexpress", AliExpressAdapter)
