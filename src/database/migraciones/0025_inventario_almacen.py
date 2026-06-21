"""
Migración 0025 — Inventario físico por almacén (INV.4.8). ADITIVA y reversible.

Añade `inventarios.id_almacen` (opcional). Si se indica, el recuento/cierre operan sobre
stock_almacen de ese almacén; si es NULL, el inventario se comporta como en INV.2
(agregado), preservando compatibilidad con inventarios existentes.
"""

VERSION = "0025"
DESCRIPCION = "Inventario físico por almacén: inventarios.id_almacen"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE inventarios ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL")
    cur.execute("ALTER TABLE inventarios ADD INDEX IF NOT EXISTS idx_inv_almacen (id_almacen)")


def revertir(cur):
    cur.execute("ALTER TABLE inventarios DROP INDEX IF EXISTS idx_inv_almacen")
    cur.execute("ALTER TABLE inventarios DROP COLUMN IF EXISTS id_almacen")
