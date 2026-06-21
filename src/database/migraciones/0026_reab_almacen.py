"""
Migración 0026 — Reabastecimiento por almacén (INV.4.7). ADITIVA y reversible.

Añade a `reab_config` referencias reales de almacén (origen/destino), conservando la
columna `origen` (texto) por compatibilidad. Permite propuestas y disponibilidad por
almacén sin romper la configuración existente ni la IA.
"""

VERSION = "0026"
DESCRIPCION = "Reabastecimiento por almacén: reab_config.id_almacen_origen/destino"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE reab_config ADD COLUMN IF NOT EXISTS id_almacen_origen INT DEFAULT NULL")
    cur.execute("ALTER TABLE reab_config ADD COLUMN IF NOT EXISTS id_almacen_destino INT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE reab_config DROP COLUMN IF EXISTS id_almacen_destino")
    cur.execute("ALTER TABLE reab_config DROP COLUMN IF EXISTS id_almacen_origen")
