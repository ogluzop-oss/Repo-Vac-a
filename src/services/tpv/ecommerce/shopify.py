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

    def _headers(self):
        return {"X-Shopify-Access-Token": self.config["api_key"],
                "Content-Type": "application/json"}

    def _location_id(self, base):
        import requests
        try:
            r = requests.get(f"{base}/admin/api/2024-01/locations.json",
                             headers=self._headers(), timeout=20)
            locs = r.json().get("locations") or []
            return locs[0].get("id") if locs else None
        except Exception as e:
            logger.warning("Shopify location: %s", e)
            return None

    def _mapa_variantes(self, base):
        """SKU → {variant_id, inventory_item_id} recorriendo el catálogo (paginado)."""
        import requests
        out, url = {}, f"{base}/admin/api/2024-01/products.json?limit=250"
        try:
            while url:
                r = requests.get(url, headers=self._headers(), timeout=25)
                if r.status_code != 200:
                    break
                for p in r.json().get("products") or []:
                    for v in p.get("variants") or []:
                        if v.get("sku"):
                            out[str(v["sku"])] = {"variant_id": v.get("id"),
                                                  "inventory_item_id": v.get("inventory_item_id")}
                # Paginación por cabecera Link (rel="next").
                link = r.headers.get("Link", "")
                url = ""
                if 'rel="next"' in link:
                    for part in link.split(","):
                        if 'rel="next"' in part:
                            url = part[part.find("<") + 1:part.find(">")]
        except Exception as e:
            logger.warning("Shopify mapa variantes: %s", e)
        return out

    def _push_variante(self, base, info, precio, stock, location_id):
        import requests
        ok = False
        if precio is not None and info.get("variant_id"):
            try:
                r = requests.put(
                    f"{base}/admin/api/2024-01/variants/{info['variant_id']}.json",
                    json={"variant": {"id": info["variant_id"], "price": f"{float(precio):.2f}"}},
                    headers=self._headers(), timeout=20)
                ok = r.status_code in (200, 201)
            except Exception as e:
                logger.warning("Shopify precio: %s", e)
        if stock is not None and info.get("inventory_item_id") and location_id:
            try:
                r = requests.post(
                    f"{base}/admin/api/2024-01/inventory_levels/set.json",
                    json={"location_id": location_id,
                          "inventory_item_id": info["inventory_item_id"],
                          "available": int(stock)},
                    headers=self._headers(), timeout=20)
                ok = ok or r.status_code in (200, 201)
            except Exception as e:
                logger.warning("Shopify stock: %s", e)
        return ok

    def actualizar_articulo(self, codigo: str, precio, stock, nombre: str = None) -> bool:
        if not self.configurado() or not codigo:
            return False
        try:
            import requests  # noqa: F401
        except Exception:
            return False
        base = self.url_web().rstrip("/")
        info = self._mapa_variantes(base).get(str(codigo))
        if not info:
            return False
        return self._push_variante(base, info, precio, stock, self._location_id(base))

    def sincronizar_catalogo(self, articulos: list) -> dict:
        """Push: mapea SKU→variante una sola vez y actualiza precio+stock."""
        if not self.configurado():
            return {"ok": False, "total": len(articulos), "actualizados": 0,
                    "fallidos": len(articulos)}
        try:
            import requests  # noqa: F401
        except Exception:
            return {"ok": False, "total": len(articulos), "actualizados": 0,
                    "fallidos": len(articulos)}
        base = self.url_web().rstrip("/")
        mapa = self._mapa_variantes(base)
        location_id = self._location_id(base)
        actualizados = 0
        for a in articulos:
            info = mapa.get(str(a.get("codigo")))
            if info and self._push_variante(base, info, a.get("precio"), a.get("stock"), location_id):
                actualizados += 1
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
