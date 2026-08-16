"""
Migración 0202 — Lonja: tipo de comercio del vendedor. ADITIVA, idempotente, reversible.

`lonja_vendedores.tipo_comercio` = lista (separada por comas) de las EDICIONES/verticales a las que el
vendedor suministra (SUPERMARKET, RETAIL, PHARMACY, TEXTIL, BAKERY). Vacío/NULL = suministra a todas.
Sirve para que sus listados/subastas SOLO aparezcan en las ediciones que correspondan.
"""

VERSION = "0202"
DESCRIPCION = "lonja_vendedores.tipo_comercio (gating de listados por edición/vertical)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "lonja_vendedores"
_COL = "tipo_comercio"


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, _TABLA, _COL):
        cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {_COL} VARCHAR(120) DEFAULT NULL")


def revertir(cur):
    if _tiene_columna(cur, _TABLA, _COL):
        cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {_COL}")
