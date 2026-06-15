"""Interfaz común de los adaptadores de e-commerce."""

import logging

logger = logging.getLogger("ecommerce.adapter")


class AdaptadorEcommerce:
    """Contrato que cumplen todos los adaptadores de plataforma."""

    nombre = "base"

    def __init__(self, config: dict):
        self.config = config or {}

    # URL de la tienda online (para el botón "Ir a la Web").
    def url_web(self) -> str:
        return (self.config.get("base_url") or "").strip()

    def configurado(self) -> bool:
        """True si hay datos suficientes para operar con la plataforma."""
        return bool(self.url_web())

    # Crea/sincroniza el pedido en la plataforma. Devuelve la referencia externa
    # (id/nº de pedido) o None si no se pudo (sin creds, sin red, plataforma 'web').
    def crear_pedido(self, pedido: dict) -> str | None:
        return None

    # Trae pedidos remotos (para sincronizar). Por defecto, ninguno.
    def listar_pedidos_remotos(self) -> list:
        return []

    # ── Push de catálogo/stock hacia la plataforma ───────────────────────────
    # Actualiza precio y existencias de UN artículo (match por SKU = código).
    # Devuelve True si se sincronizó. Por defecto no hace nada (web propia).
    def actualizar_articulo(self, codigo: str, precio, stock, nombre: str = None) -> bool:
        return False

    def sincronizar_catalogo(self, articulos: list) -> dict:
        """Empuja precio+stock de una lista de artículos a la plataforma.

        ``articulos`` = [{codigo, nombre, precio, stock}]. Devuelve
        {ok, total, actualizados, fallidos}. Implementación por defecto: itera
        ``actualizar_articulo`` (los adaptadores pueden sobrescribir con batch)."""
        if not self.configurado():
            return {"ok": False, "total": len(articulos), "actualizados": 0,
                    "fallidos": len(articulos)}
        actualizados = 0
        for a in articulos:
            try:
                if self.actualizar_articulo(a.get("codigo"), a.get("precio"),
                                            a.get("stock"), a.get("nombre")):
                    actualizados += 1
            except Exception:
                pass
        return {"ok": True, "total": len(articulos), "actualizados": actualizados,
                "fallidos": len(articulos) - actualizados}
