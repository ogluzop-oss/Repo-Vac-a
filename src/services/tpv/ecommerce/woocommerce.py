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

    def _auth(self):
        return (self.config["api_key"], self.config["api_secret"])

    def _producto_id_por_sku(self, base, sku):
        """ID de producto de WooCommerce a partir del SKU (= código). None si no existe."""
        import requests
        try:
            r = requests.get(f"{base}/wp-json/wc/v3/products", params={"sku": sku},
                             auth=self._auth(), timeout=20)
            if r.status_code == 200 and r.json():
                return r.json()[0].get("id")
        except Exception as e:
            logger.warning("Woo buscar SKU %s: %s", sku, e)
        return None

    def actualizar_articulo(self, codigo: str, precio, stock, nombre: str = None) -> bool:
        if not self.configurado() or not codigo:
            return False
        try:
            import requests
        except Exception:
            return False
        base = self.url_web().rstrip("/")
        pid = self._producto_id_por_sku(base, codigo)
        if not pid:
            return False
        payload = {"manage_stock": True}
        if precio is not None:
            payload["regular_price"] = f"{float(precio):.2f}"
        if stock is not None:
            payload["stock_quantity"] = int(stock)
        try:
            r = requests.put(f"{base}/wp-json/wc/v3/products/{pid}", json=payload,
                             auth=self._auth(), timeout=20)
            return r.status_code in (200, 201)
        except Exception as e:
            logger.warning("Woo actualizar_articulo %s: %s", codigo, e)
            return False

    def sincronizar_catalogo(self, articulos: list) -> dict:
        """Push en lote: mapea SKU→id y usa el endpoint batch de WooCommerce."""
        if not self.configurado():
            return {"ok": False, "total": len(articulos), "actualizados": 0,
                    "fallidos": len(articulos)}
        try:
            import requests
        except Exception:
            return {"ok": False, "total": len(articulos), "actualizados": 0,
                    "fallidos": len(articulos)}
        base = self.url_web().rstrip("/")
        # Mapa SKU→id recorriendo el catálogo remoto (paginado).
        sku2id, page = {}, 1
        try:
            while True:
                r = requests.get(f"{base}/wp-json/wc/v3/products",
                                 params={"per_page": 100, "page": page},
                                 auth=self._auth(), timeout=25)
                if r.status_code != 200 or not r.json():
                    break
                for p in r.json():
                    if p.get("sku"):
                        sku2id[str(p["sku"])] = p.get("id")
                if len(r.json()) < 100:
                    break
                page += 1
        except Exception as e:
            logger.warning("Woo sincronizar_catalogo (mapa): %s", e)
        updates = []
        for a in articulos:
            pid = sku2id.get(str(a.get("codigo")))
            if not pid:
                continue
            u = {"id": pid, "manage_stock": True}
            if a.get("precio") is not None:
                u["regular_price"] = f"{float(a['precio']):.2f}"
            if a.get("stock") is not None:
                u["stock_quantity"] = int(a["stock"])
            updates.append(u)
        actualizados = 0
        for i in range(0, len(updates), 100):       # batch de 100 en 100
            lote = updates[i:i + 100]
            try:
                r = requests.post(f"{base}/wp-json/wc/v3/products/batch",
                                  json={"update": lote}, auth=self._auth(), timeout=40)
                if r.status_code in (200, 201):
                    actualizados += len(r.json().get("update", lote))
            except Exception as e:
                logger.warning("Woo batch: %s", e)
        return {"ok": True, "total": len(articulos), "actualizados": actualizados,
                "fallidos": len(articulos) - actualizados}

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
                auth=self._auth(), timeout=20)
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
