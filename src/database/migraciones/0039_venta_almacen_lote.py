"""
Migracion 0039 - Venta multialmacen/lote (VTA.5). ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0039"
DESCRIPCION = "Venta multialmacen/lote (VTA.5)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL")
    cur.execute("ALTER TABLE venta_items ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL")
    cur.execute("ALTER TABLE venta_items ADD COLUMN IF NOT EXISTS id_lote BIGINT DEFAULT NULL")
    cur.execute("ALTER TABLE devolucion_items ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL")
    cur.execute("ALTER TABLE devolucion_items ADD COLUMN IF NOT EXISTS id_lote BIGINT DEFAULT NULL")


def revertir(cur):
    for t, c in (("ventas","id_almacen"),("venta_items","id_almacen"),("venta_items","id_lote"),("devolucion_items","id_almacen"),("devolucion_items","id_lote")):
        cur.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS {c}")
