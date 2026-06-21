"""
Migración 0024 — Lotes por almacén (INV.4.4). ADITIVA y reversible.

Añade `lotes.id_almacen` (dimensión de almacén para los lotes) e índice asociado, y
realiza un backfill best-effort asociando los lotes existentes al almacén de su tienda.
Mantiene el UNIQUE de INV.3 (empresa,tienda,codigo,lote) para compatibilidad total: el
id_almacen es una dimensión añadida y filtro de consumo FEFO, no rompe lo existente.
"""

VERSION = "0024"
DESCRIPCION = "Lotes por almacén: lotes.id_almacen + backfill"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE lotes ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL")
    cur.execute("ALTER TABLE lotes ADD INDEX IF NOT EXISTS idx_lote_almacen (id_empresa, id_almacen)")
    # Backfill: lote con tienda → almacén tipo 'tienda' de esa tienda.
    cur.execute("""
        UPDATE lotes l
        JOIN almacen a ON a.id_empresa=l.id_empresa AND a.tipo_almacen='tienda'
                       AND a.id_tienda=l.id_tienda
        SET l.id_almacen = a.id
        WHERE l.id_almacen IS NULL AND l.id_tienda<>0
    """)


def revertir(cur):
    cur.execute("ALTER TABLE lotes DROP INDEX IF EXISTS idx_lote_almacen")
    cur.execute("ALTER TABLE lotes DROP COLUMN IF EXISTS id_almacen")
