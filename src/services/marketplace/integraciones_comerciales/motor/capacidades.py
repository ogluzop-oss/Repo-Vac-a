"""
Motor · CAPACIDADES por conector (Fase WEB-13). Cada plataforma DECLARA (metadatos) qué capacidades soporta.
Toda la arquitectura trabaja por capacidades — NUNCA ramificando por plataforma. Sin lógica de conexión.
"""

from dataclasses import asdict, dataclass, fields

# Nombres canónicos de capacidades (matriz única).
CAPACIDADES_NOMBRES = (
    "supports_products", "supports_orders", "supports_customers", "supports_inventory",
    "supports_prices", "supports_click_collect", "supports_web_creation", "supports_domain",
    "supports_ssl", "supports_ai_generation", "supports_reviews", "supports_tracking",
    "supports_returns", "supports_notifications",
)


@dataclass(frozen=True)
class ConnectorCapabilities:
    """Matriz de capacidades de un conector (todas False por defecto)."""
    supports_products: bool = False
    supports_orders: bool = False
    supports_customers: bool = False
    supports_inventory: bool = False
    supports_prices: bool = False
    supports_click_collect: bool = False
    supports_web_creation: bool = False
    supports_domain: bool = False
    supports_ssl: bool = False
    supports_ai_generation: bool = False
    supports_reviews: bool = False
    supports_tracking: bool = False
    supports_returns: bool = False
    supports_notifications: bool = False

    def soporta(self, nombre: str) -> bool:
        return bool(getattr(self, nombre, False))

    def soportadas(self) -> list:
        return [f.name for f in fields(self) if getattr(self, f.name)]

    def as_dict(self) -> dict:
        return asdict(self)


# Perfiles reutilizables (sin duplicar listas de flags).
def _ecommerce_autohospedado(**extra) -> ConnectorCapabilities:
    base = dict(supports_products=True, supports_orders=True, supports_customers=True,
                supports_inventory=True, supports_prices=True, supports_click_collect=True,
                supports_reviews=True, supports_tracking=True, supports_returns=True,
                supports_notifications=True)
    base.update(extra)
    return ConnectorCapabilities(**base)


def _marketplace_tercero(**extra) -> ConnectorCapabilities:
    base = dict(supports_products=True, supports_orders=True, supports_customers=True,
                supports_inventory=True, supports_prices=True, supports_tracking=True,
                supports_returns=True, supports_notifications=True)
    base.update(extra)
    return ConnectorCapabilities(**base)


# Registro declarativo plataforma → capacidades.
_REGISTRO = {
    "hostinger": ConnectorCapabilities(supports_web_creation=True, supports_domain=True,
                                       supports_ssl=True, supports_ai_generation=True,
                                       supports_notifications=True),
    "woocommerce": _ecommerce_autohospedado(),
    "shopify": _ecommerce_autohospedado(supports_domain=True, supports_ssl=True),
    "prestashop": _ecommerce_autohospedado(),
    "magento": _ecommerce_autohospedado(),
    "opencart": _ecommerce_autohospedado(),
    "amazon": _marketplace_tercero(),
    "ebay": _marketplace_tercero(),
    "miravia": _marketplace_tercero(),
    "aliexpress": _marketplace_tercero(),
    "tiktok_shop": _marketplace_tercero(),
}


def capacidades(plataforma: str) -> ConnectorCapabilities:
    """Capacidades declaradas de una plataforma (todas False si no está registrada)."""
    return _REGISTRO.get((plataforma or "").lower(), ConnectorCapabilities())


def registrar(plataforma: str, caps: ConnectorCapabilities) -> None:
    """Registra/actualiza las capacidades de una plataforma (extensibilidad sin tocar el motor)."""
    _REGISTRO[(plataforma or "").lower()] = caps


def matriz() -> dict:
    """Matriz completa plataforma → {capacidad: bool}."""
    return {k: v.as_dict() for k, v in _REGISTRO.items()}
