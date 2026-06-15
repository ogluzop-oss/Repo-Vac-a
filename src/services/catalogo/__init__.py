"""
Servicio de CATÁLOGO ONLINE (Fase 2 — omnicanal).

Capa de servicio neutra entre los datos del catálogo (`src.db.catalogo`, overlay
sobre `articulos`) y cualquier presentación: web pública del cliente, panel
operativo interno y conectores de e-commerce (Escenarios A y B).

Expone dos serializaciones de un mismo producto según el rol autenticado:
- `vista_publica`  → datos de escaparate (precio, disponibilidad, promos…).
- `vista_operativa`→ datos internos (stock real por tienda, reservas, estados…).
"""

from src.services.catalogo.service import (buscar, destacados,
                                           disponibilidad_por_tienda,
                                           es_vista_interna, listar_categorias,
                                           listar_productos, producto,
                                           recomendados, serializar,
                                           vista_operativa, vista_publica)

__all__ = ["listar_categorias", "listar_productos", "producto", "destacados",
           "recomendados", "buscar", "vista_publica", "vista_operativa",
           "disponibilidad_por_tienda", "es_vista_interna", "serializar"]
