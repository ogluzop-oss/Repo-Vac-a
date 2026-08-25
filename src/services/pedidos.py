"""
Servicio de PEDIDOS DE RECEPCIÓN (palets). Capa fina sobre `src/db/pedidos.py`.

IMPORTANTE (honestidad de dominio): en Smart Manager, la tabla `pedidos` es la unidad de RECEPCIÓN de
mercancía por palet (escaneo RFID/código en almacén: `pale_codigo` + `items`), NO un pedido de venta a
cliente ni de compra a proveedor. Es, hoy, el único modelo real de "pedido" en la base de datos — de
ahí que la capacidad "pedidos" del catálogo móvil (`/api/v1/orders`) se sirva con este dominio.
"""


def listar(id_empresa, id_tienda=None, procesado: bool | None = None, limite: int = 100) -> list[dict]:
    """Pedidos de recepción de la empresa (más recientes primero), opcionalmente filtrados por
    tienda y por si ya se procesaron (se volcaron a stock) o no."""
    from src.db import pedidos as _db
    return _db.listar_pedidos(id_empresa=id_empresa, id_tienda=id_tienda,
                              procesado=procesado, limite=limite)
