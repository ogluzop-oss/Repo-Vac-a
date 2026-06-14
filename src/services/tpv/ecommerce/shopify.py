"""Adaptador Shopify (Admin REST API).

base_url = https://mitienda.myshopify.com ; api_key = Admin API access token.
Crea el pedido vía POST /admin/api/2024-01/orders.json. Degrada con elegancia.
"""

import logging

from src.services.tpv.ecommerce.base import AdaptadorEcommerce

logger = logging.getLogger("ecommerce.shopify")


class AdaptadorShopify(AdaptadorEcommerce):
    nombre = "shopify"

    def configurado(self) -> bool:
        return bool(self.url_web() and self.config.get("api_key"))

    def crear_pedido(self, pedido: dict) -> str | None:
        if not self.configurado():
            return None
        try:
            import requests
        except Exception:
            return None
        base = self.url_web().rstrip("/")
        payload = {"order": {
            "email": pedido.get("cliente_email") or None,
            "financial_status": "paid" if pedido.get("estado") == "PAGADO" else "pending",
            "line_items": [
                {"title": it.get("nombre") or it.get("codigo_articulo") or "Artículo",
                 "quantity": int(it.get("cantidad", 1)),
                 "price": f"{float(it.get('precio_unitario', 0)):.2f}"}
                for it in pedido.get("items", [])
            ],
            "note": f"Smart Manager ref: {pedido.get('id_pedido')}",
            "shipping_address": {"address1": pedido.get("direccion_envio") or "",
                                 "name": pedido.get("cliente_nombre") or ""},
        }}
        try:
            resp = requests.post(
                f"{base}/admin/api/2024-01/orders.json", json=payload,
                headers={"X-Shopify-Access-Token": self.config["api_key"],
                         "Content-Type": "application/json"}, timeout=20)
            if resp.status_code in (200, 201):
                return str((resp.json().get("order") or {}).get("id") or "")
            logger.warning("Shopify respondió %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Shopify crear_pedido falló: %s", e)
        return None
