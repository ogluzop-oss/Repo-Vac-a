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

    @staticmethod
    def _estado(o: dict) -> str:
        """Estado interno a partir de financial_status / fulfillment_status / cancel."""
        if o.get("cancelled_at"):
            return "CANCELADO"
        ful = o.get("fulfillment_status")
        fin = o.get("financial_status")
        if ful == "fulfilled":
            return "ENTREGADO"
        if fin in ("paid", "partially_paid"):
            return "PAGADO"
        return "PENDIENTE"

    def listar_pedidos_remotos(self) -> list:
        if not self.configurado():
            return []
        try:
            import requests
        except Exception:
            return []
        base = self.url_web().rstrip("/")
        try:
            resp = requests.get(
                f"{base}/admin/api/2024-01/orders.json", params={"status": "any", "limit": 50},
                headers={"X-Shopify-Access-Token": self.config["api_key"]}, timeout=20)
            if resp.status_code != 200:
                logger.warning("Shopify listar respondió %s", resp.status_code)
                return []
            out = []
            for o in (resp.json().get("orders") or []):
                cli = o.get("customer") or {}
                nombre = " ".join(x for x in (cli.get("first_name"), cli.get("last_name")) if x)
                envio = o.get("shipping_address") or {}
                out.append({
                    "referencia_externa": str(o.get("id") or ""),
                    "cliente_nombre": nombre or None,
                    "cliente_telefono": cli.get("phone") or envio.get("phone") or None,
                    "cliente_email": o.get("email") or cli.get("email") or None,
                    "direccion_envio": envio.get("address1") or None,
                    "total": float(o.get("total_price") or 0),
                    "estado": self._estado(o),
                    "fecha": o.get("created_at"),
                    "items": [{"codigo": it.get("sku") or None, "nombre": it.get("title"),
                               "cantidad": int(it.get("quantity", 1) or 1),
                               "precio": float(it.get("price") or 0),
                               "subtotal": float(it.get("price") or 0) * int(it.get("quantity", 1) or 1)}
                              for it in (o.get("line_items") or [])],
                })
            return out
        except Exception as e:
            logger.warning("Shopify listar_pedidos_remotos falló: %s", e)
            return []
