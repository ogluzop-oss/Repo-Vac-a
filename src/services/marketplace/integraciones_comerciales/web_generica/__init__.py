"""
Marketplace · Integraciones Comerciales · Conector **Web genérica / tradicional** (2 modos: feed y REST).

Se registra en el motor WEB-13 por su PUNTO DE EXTENSIÓN público (``registrar_adaptador``), SIN tocar el motor
(igual que WooCommerce/Amazon/…). Arquitectura PREPARADA/degradable. Aparece automáticamente en el catálogo de
plataformas (tipo ``web_tradicional``) y en el asistente "Añadir integración".
"""

from src.services.marketplace.integraciones_comerciales.web_generica import (  # noqa: F401
    feed, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.web_generica.adaptador import (  # noqa: F401
    WebFeedAdapter, WebRestAdapter)


def registrar() -> None:
    """Registra los conectores de web tradicional (feed + REST) en el motor. Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("web_feed", WebFeedAdapter)
    registrar_adaptador("web_rest", WebRestAdapter)
