"""
Migración 0190 — Emoji representativo por artículo. ADITIVA, idempotente, reversible.

Añade `articulos.emoji` (VARCHAR corto, opcional) para mostrar un icono junto al producto en el TPV táctil
(rejilla bakery). No afecta a la lógica de venta/stock; es puramente presentacional.
"""

VERSION = "0190"
DESCRIPCION = "Emoji representativo por artículo (articulos.emoji) para el TPV táctil"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "articulos", "emoji"):
        cur.execute("ALTER TABLE articulos ADD COLUMN emoji VARCHAR(16) DEFAULT NULL")


def revertir(cur):
    if _tiene_columna(cur, "articulos", "emoji"):
        cur.execute("ALTER TABLE articulos DROP COLUMN emoji")
