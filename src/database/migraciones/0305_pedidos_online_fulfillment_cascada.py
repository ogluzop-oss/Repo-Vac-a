"""
Migración 0305 — Reparto en cascada de pedidos online entre tiendas/almacenes. ADITIVA,
idempotente, reversible.

Soporta el enrutado de un pedido de la web/Marketplace a la tienda MÁS CERCANA con stock
(`buscar_almacenes_con_stock`, ya existente) y, si esa tienda no puede suministrar la cantidad
COMPLETA, la creación automática de un pedido de CONTINUACIÓN por la cantidad restante hacia la
siguiente tienda más cercana con stock — repitiendo hasta cubrir el pedido (envío conjunto desde
varias tiendas al mismo cliente). Cada tienda confirma MANUAL y OBLIGATORIAMENTE cuánto puede
suministrar realmente (nunca se asume automáticamente a partir del stock teórico).

- `pedidos_online.id_pedido_origen`: referencia al pedido ORIGINAL de la cadena (NULL si este
  pedido no es una continuación de otro). Permite reconstruir la cadena completa de un envío
  conjunto multi-tienda sin tocar ninguna columna existente.
- `pedidos_online_items.cantidad_servida`: cantidad que la tienda ha confirmado MANUALMENTE que
  puede suministrar de esta línea (NULL = aún sin confirmar). Si < `cantidad`, dispara la
  creación del pedido de continuación por la diferencia.
"""

VERSION = "0305"
DESCRIPCION = ("Pedidos online: id_pedido_origen (cadena de continuaciones) + "
               "pedidos_online_items.cantidad_servida (confirmación manual por tienda)")
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE pedidos_online "
                "ADD COLUMN IF NOT EXISTS id_pedido_origen VARCHAR(36) DEFAULT NULL "
                "AFTER referencia_externa")
    cur.execute("ALTER TABLE pedidos_online_items "
                "ADD COLUMN IF NOT EXISTS cantidad_servida INT DEFAULT NULL AFTER id_almacen")
    cur.execute("ALTER TABLE pedidos_online "
                "ADD INDEX IF NOT EXISTS idx_po_origen (id_pedido_origen)")


def revertir(cur):
    cur.execute("ALTER TABLE pedidos_online DROP INDEX IF EXISTS idx_po_origen")
    cur.execute("ALTER TABLE pedidos_online DROP COLUMN IF EXISTS id_pedido_origen")
    cur.execute("ALTER TABLE pedidos_online_items DROP COLUMN IF EXISTS cantidad_servida")
