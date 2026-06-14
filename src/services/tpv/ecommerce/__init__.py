"""
Adaptadores de e-commerce (F2) — multiplataforma y enchufables.

`adaptador_actual()` devuelve el adaptador de la plataforma configurada para la
empresa activa (web propia / WooCommerce / Shopify / PrestaShop). Todos cumplen
la interfaz `AdaptadorEcommerce` y degradan con elegancia (sin credenciales o sin
red, no rompen: registran el pedido localmente y devuelven None).
"""

from src.services.tpv.ecommerce.factory import adaptador_actual, adaptador_para

__all__ = ["adaptador_actual", "adaptador_para"]
