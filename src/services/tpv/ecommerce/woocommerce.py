"""Adaptador WooCommerce (REST API v3).

base_url = URL de la tienda (https://mitienda.com); api_key/api_secret =
consumer key/secret de la API REST de WooCommerce. Crea el pedido vía
POST /wp-json/wc/v3/orders. Degrada con elegancia si faltan datos o falla la red.
"""

import logging

from src.services.tpv.ecommerce.base import AdaptadorEcommerce

logger = logging.getLogger("ecommerce.woo")


class AdaptadorWooCommerce(AdaptadorEcommerce):
    nombre = "woocommerce"

    def configurado(self) -> bool:
        return bool(self.url_web() and self.config.get("api_key") and self.config.get("api_secret"))

    def crear_pedido(self, pedido: dict) -> str | None:
        if not self.configurado():
            return None
        try:
            import requests
        except Exception:
            logger.warning("requests no disponible; pedido Woo no sincronizado.")
            return None
        base = self.url_web().rstrip("/")
        nombre = (pedido.get("cliente_nombre") or "Cliente").split()
        payload = {
            "status": "processing" if pedido.get("estado") == "PAGADO" else "pending",
            "billing": {
                "first_name": nombre[0] if nombre else "Cliente",
                "last_name": " ".join(nombre[1:]) if len(nombre) > 1 else "",
                "email": pedido.get("cliente_email") or "",
                "phone": pedido.get("cliente_telefono") or "",
                "address_1": pedido.get("direccion_envio") or "",
            },
            "line_items": [
                {"name": it.get("nombre") or it.get("codigo_articulo") or "Artículo",
                 "quantity": int(it.get("cantidad", 1)),
                 "total": f"{float(it.get('subtotal', 0)):.2f}"}
                for it in pedido.get("items", [])
            ],
            "meta_data": [{"key": "smart_manager_ref", "value": pedido.get("id_pedido")}],
        }
        try:
            resp = requests.post(
                f"{base}/wp-json/wc/v3/orders", json=payload,
                auth=(self.config["api_key"], self.config["api_secret"]), timeout=20)
            if resp.status_code in (200, 201):
                return str(resp.json().get("id") or "")
            logger.warning("WooCommerce respondió %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("WooCommerce crear_pedido falló: %s", e)
        return None

    # Mapeo de estados de WooCommerce a los estados internos.
    _ESTADOS = {"pending": "PENDIENTE", "on-hold": "PENDIENTE", "processing": "PAGADO",
                "completed": "ENTREGADO", "cancelled": "CANCELADO",
                "refunded": "CANCELADO", "failed": "CANCELADO"}

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
                f"{base}/wp-json/wc/v3/orders", params={"per_page": 50, "orderby": "date"},
                auth=(self.config["api_key"], self.config["api_secret"]), timeout=20)
            if resp.status_code != 200:
                logger.warning("WooCommerce listar respondió %s", resp.status_code)
                return []
            out = []
            for o in resp.json() or []:
                b = o.get("billing") or {}
                nombre = " ".join(x for x in (b.get("first_name"), b.get("last_name")) if x)
                out.append({
                    "referencia_externa": str(o.get("id") or ""),
                    "cliente_nombre": nombre or None,
                    "cliente_telefono": b.get("phone") or None,
                    "cliente_email": b.get("email") or None,
                    "direccion_envio": b.get("address_1") or None,
                    "total": float(o.get("total") or 0),
                    "estado": self._ESTADOS.get(o.get("status"), "PENDIENTE"),
                    "fecha": o.get("date_created"),
                    "items": [{"codigo": it.get("sku") or None, "nombre": it.get("name"),
                               "cantidad": int(it.get("quantity", 1) or 1),
                               "precio": float(it.get("price") or 0),
                               "subtotal": float(it.get("total") or 0)}
                              for it in (o.get("line_items") or [])],
                })
            return out
        except Exception as e:
            logger.warning("WooCommerce listar_pedidos_remotos falló: %s", e)
            return []
