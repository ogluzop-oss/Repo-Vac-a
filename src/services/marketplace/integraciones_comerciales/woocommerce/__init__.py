"""
Marketplace · Integraciones Comerciales · **Conector WooCommerce** (Fase WEB-15) — primer conector comercial
real para empresas que YA tienen tienda online.

Implementa el adaptador WooCommerce SOBRE el motor WEB-13 (sin modificarlo) y el patrón del adaptador
Hostinger (WEB-14): transporte HTTP inyectable, secretos vía SecretManager, estados/errores/auditoría del
motor. **Reutiliza los motores existentes del ERP**: productos (`db.catalogo.upsert_producto`, idempotente por
SKU), clientes (`db.clientes`, sin duplicados), pedidos (`online_orders_service.crear_pedido_online` — el MISMO
pedido que llega desde TPV/Portal Web/Canal Web), stock (`db.stock_almacen`). Multiempresa/multitienda.

Honestidad (patrón degradable): las llamadas son REALES (WooCommerce REST API, Consumer Key/Secret); el
adaptador está `disponible()` SOLO con credenciales + URL reales. Sin ellas → `MISSING_CREDENTIALS`, sin red.
"""

from src.services.marketplace.integraciones_comerciales.woocommerce import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.woocommerce.adaptador import \
    WooCommerceAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.woocommerce.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el conector WooCommerce en el motor (punto de extensión público de WEB-13). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("woocommerce", WooCommerceAdapter)
