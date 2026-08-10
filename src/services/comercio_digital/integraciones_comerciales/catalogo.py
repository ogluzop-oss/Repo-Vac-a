"""
Integraciones Comerciales · Catálogo de PLATAFORMAS (Fase WEB-02). Descriptores de las plataformas externas
soportadas/previstas. Todo en estado **PREPARADO** (ninguna integración implementada). Marketplace consumirá
este catálogo en su apartado "Integraciones Comerciales"; el Canal Web sólo redirige aquí.
"""

# tipo: 'ecommerce' (tienda propia externa) | 'marketplace' (mercado de terceros) |
#       'web_tradicional' (web propia con OTRO proveedor: Wix/WordPress/Squarespace/a medida — 2 modos:
#        feed de catálogo para escaparates SIN API, o REST para webs con endpoints).
PLATAFORMAS = (
    {"clave": "woocommerce", "nombre": "WooCommerce", "tipo": "ecommerce", "estado": "preparado"},
    {"clave": "shopify", "nombre": "Shopify", "tipo": "ecommerce", "estado": "preparado"},
    {"clave": "prestashop", "nombre": "PrestaShop", "tipo": "ecommerce", "estado": "preparado"},
    {"clave": "magento", "nombre": "Magento", "tipo": "ecommerce", "estado": "preparado"},
    {"clave": "opencart", "nombre": "OpenCart", "tipo": "ecommerce", "estado": "preparado"},
    {"clave": "amazon", "nombre": "Amazon", "tipo": "marketplace", "estado": "preparado"},
    {"clave": "ebay", "nombre": "eBay", "tipo": "marketplace", "estado": "preparado"},
    {"clave": "miravia", "nombre": "Miravia", "tipo": "marketplace", "estado": "preparado"},
    {"clave": "aliexpress", "nombre": "AliExpress", "tipo": "marketplace", "estado": "preparado"},
    {"clave": "tiktok_shop", "nombre": "TikTok Shop", "tipo": "marketplace", "estado": "preparado"},
    {"clave": "web_feed", "nombre": "Web propia · Catálogo (feed)", "tipo": "web_tradicional",
     "estado": "preparado"},
    {"clave": "web_rest", "nombre": "Web propia · API (REST)", "tipo": "web_tradicional",
     "estado": "preparado"},
)

_POR_CLAVE = {p["clave"]: p for p in PLATAFORMAS}


def listar(tipo=None) -> list:
    return [dict(p) for p in PLATAFORMAS if tipo is None or p["tipo"] == tipo]


def obtener(clave) -> dict | None:
    p = _POR_CLAVE.get((clave or "").lower())
    return dict(p) if p else None
