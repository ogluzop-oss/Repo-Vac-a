"""
Marketplace · Integraciones Comerciales · **Conector Miravia** (Fase WEB-22) — MARKETPLACE (canal de venta
externo). Replica EXACTAMENTE el patrón consolidado (Amazon/eBay + ecommerce). Toda la lógica específica de
Miravia vive SOLO aquí (`miravia/`).

RESPONSABILIDAD (marketplace): sincroniza productos/pedidos/clientes/stock/precios/estados. **NO** crea webs,
dominios, SSL ni tiendas (eso es de Hostinger). Reutiliza el motor WEB-13, el SecretManager y los MOTORES del
ERP. Degradable: `disponible()` = True solo con Access Token real; sin él → `MISSING_CREDENTIALS`, sin red.
Aparece automáticamente en el Centro (WEB-16.5).

Honestidad: la API de Miravia (plataforma abierta tipo Alibaba/TOP) usa app_key/app_secret + firma/sesión;
esta estructura queda operativa-ready y degradable (bloqueo externo de credenciales), sin falsear conexiones.
"""

from src.services.marketplace.integraciones_comerciales.miravia import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.miravia.adaptador import \
    MiraviaAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.miravia.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector Miravia en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("miravia", MiraviaAdapter)
