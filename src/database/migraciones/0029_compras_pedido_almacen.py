"""
Migración 0029 — Pedido de compra con almacén destino y descuento (CMP.2). ADITIVA.

Añade `compras_pedidos.id_almacen` (almacén destino) y `descuento` (% aplicado del
proveedor). No elimina ni cambia nada existente.
"""

VERSION = "0029"
DESCRIPCION = "Compras: compras_pedidos.id_almacen + descuento"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE compras_pedidos ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL")
    cur.execute("ALTER TABLE compras_pedidos ADD COLUMN IF NOT EXISTS descuento DECIMAL(5,2) NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE compras_pedidos ADD INDEX IF NOT EXISTS idx_ped_almacen (id_almacen)")


def revertir(cur):
    cur.execute("ALTER TABLE compras_pedidos DROP INDEX IF EXISTS idx_ped_almacen")
    cur.execute("ALTER TABLE compras_pedidos DROP COLUMN IF EXISTS descuento")
    cur.execute("ALTER TABLE compras_pedidos DROP COLUMN IF EXISTS id_almacen")
