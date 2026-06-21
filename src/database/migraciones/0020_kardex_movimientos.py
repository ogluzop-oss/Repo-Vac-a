"""
Migración 0020 — Kárdex unificado de movimientos (INV.1). ADITIVA e idempotente.

`movimientos_stock` ya disponía de id_empresa/id_tienda/id_almacen_* (parches previos).
Esta migración solo añade el rastro de ajuste (stock_anterior/stock_nuevo) e índices de
consulta para el visor/informes. No altera datos ni la lógica de stock.
"""

VERSION = "0020"
DESCRIPCION = "Kárdex: stock_anterior/stock_nuevo + índices en movimientos_stock"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("stock_anterior", "INT DEFAULT NULL"),
    ("stock_nuevo", "INT DEFAULT NULL"),
]
_IDX = [
    ("idx_ms_tipo", "tipo_movimiento"),
    ("idx_ms_fecha", "fecha_movimiento"),
    ("idx_ms_empresa", "id_empresa"),
    ("idx_ms_tienda", "id_tienda"),
    ("idx_ms_usuario", "usuario"),
]


def aplicar(cur):
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE movimientos_stock ADD COLUMN IF NOT EXISTS {col} {ddl}")
    for nombre, col in _IDX:
        cur.execute(f"ALTER TABLE movimientos_stock ADD INDEX IF NOT EXISTS {nombre} ({col})")


def revertir(cur):
    for nombre, _ in _IDX:
        cur.execute(f"ALTER TABLE movimientos_stock DROP INDEX IF EXISTS {nombre}")
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE movimientos_stock DROP COLUMN IF EXISTS {col}")
