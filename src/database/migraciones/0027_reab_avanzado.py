"""
Migración 0027 — Reabastecimiento avanzado (INV.6.1). ADITIVA e idempotente.

Amplía `reab_config` con stock_maximo, punto_pedido, lead_time_dias e id_proveedor_preferente,
y `reab_propuestas` con almacén origen/destino y previsión utilizada. No cambia PKs ni
elimina nada; conserva umbral_min/stock_objetivo de INV anteriores como respaldo.
"""

VERSION = "0027"
DESCRIPCION = "Reab avanzado: reab_config (max/punto/lead/proveedor) + reab_propuestas (almacén/previsión)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_CFG = [
    ("stock_maximo", "INT NOT NULL DEFAULT 0"),
    ("punto_pedido", "INT NOT NULL DEFAULT 0"),
    ("lead_time_dias", "INT NOT NULL DEFAULT 0"),
    ("id_proveedor_preferente", "INT DEFAULT NULL"),
]
_PROP = [
    ("id_almacen_origen", "INT DEFAULT NULL"),
    ("id_almacen_destino", "INT DEFAULT NULL"),
    ("prevision_usada", "INT DEFAULT NULL"),
]


def aplicar(cur):
    for col, ddl in _CFG:
        cur.execute(f"ALTER TABLE reab_config ADD COLUMN IF NOT EXISTS {col} {ddl}")
    for col, ddl in _PROP:
        cur.execute(f"ALTER TABLE reab_propuestas ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _PROP:
        cur.execute(f"ALTER TABLE reab_propuestas DROP COLUMN IF EXISTS {col}")
    for col, _ in _CFG:
        cur.execute(f"ALTER TABLE reab_config DROP COLUMN IF EXISTS {col}")
