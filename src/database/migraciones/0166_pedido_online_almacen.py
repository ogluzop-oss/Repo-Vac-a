"""
Migración 0166 — Pedidos online: ALMACÉN de origen por línea. ADITIVA e IDEMPOTENTE.

Añade `id_almacen` a `pedidos_online_items` para registrar de qué almacén (stock físico, elegido por el
trabajador al crear el pedido) se sirve cada artículo. No cambia datos existentes (columna NULL).
"""

VERSION = "0166"
DESCRIPCION = "Pedidos online: columna id_almacen en pedidos_online_items (almacén de origen por línea)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE pedidos_online_items "
                "ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL AFTER origen_stock")


def revertir(cur):
    cur.execute("ALTER TABLE pedidos_online_items DROP COLUMN IF EXISTS id_almacen")
