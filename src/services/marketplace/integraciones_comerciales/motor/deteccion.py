"""
Motor · DETECCIÓN AUTOMÁTICA de plataforma (Fase WEB-13). Arquitectura para deducir la plataforma de una URL
(WooCommerce/Shopify/PrestaShop/Magento/OpenCart…) a partir de FIRMAS declarativas. **NO realiza llamadas
HTTP**: `detectar()` solo casa contra `señales` ya observadas (que un detector real aportaría en el futuro);
sin señales, devuelve el conjunto de candidatos PREPARADO para sondeo. Dirigido por firmas, no por comparación literal de URL.
"""

# Firma declarativa por plataforma: marcadores que un sondeo futuro buscaría (paths, cabeceras, meta, etc.).
FIRMAS = {
    "woocommerce": {"marcadores": ("/wp-json/wc/", "woocommerce", "wp-content/plugins/woocommerce")},
    "shopify": {"marcadores": ("myshopify.com", "/cart.js", "x-shopify-stage", "cdn.shopify.com")},
    "prestashop": {"marcadores": ("/js/prestashop", "prestashop", "id_product")},
    "magento": {"marcadores": ("/static/version", "mage/", "magento")},
    "opencart": {"marcadores": ("index.php?route=", "catalog/view", "opencart")},
}


def _normaliza(señales) -> str:
    if señales is None:
        return ""
    if isinstance(señales, dict):
        return " ".join(str(v) for v in señales.values()).lower()
    if isinstance(señales, (list, tuple, set)):
        return " ".join(str(v) for v in señales).lower()
    return str(señales).lower()


def detectar(url: str, señales=None) -> dict:
    """Detecta la plataforma a partir de `señales` YA observadas (sin realizar ninguna petición). Si no se
    aportan señales, devuelve los candidatos y marca `requiere_sondeo` (el sondeo real llegará en fases
    posteriores). Nunca accede a la red."""
    blob = _normaliza(señales)
    candidatos = list(FIRMAS)
    if not blob:
        return {"url": url, "plataforma": None, "estado": "PREPARADO", "requiere_sondeo": True,
                "candidatos": candidatos}
    coincidencias = [p for p, f in FIRMAS.items()
                     if any(m.lower() in blob for m in f["marcadores"])]
    return {"url": url, "plataforma": coincidencias[0] if coincidencias else None,
            "estado": "DETECTADA" if coincidencias else "DESCONOCIDA",
            "requiere_sondeo": False, "coincidencias": coincidencias, "candidatos": candidatos}


def registrar_firma(plataforma: str, marcadores) -> None:
    """Extensibilidad: añadir/actualizar la firma de una plataforma sin tocar el detector."""
    FIRMAS[(plataforma or "").lower()] = {"marcadores": tuple(marcadores)}
