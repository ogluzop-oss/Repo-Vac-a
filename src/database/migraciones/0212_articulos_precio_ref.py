"""
Migración 0212 — Precio de referencia manual por artículo. ADITIVA, idempotente, reversible.

`articulos.precio_ref` guarda el Precio ref. FIJADO MANUALMENTE por la empresa (lonjas/Mercabarna/
comparadores). Si es NULL, el Precio ref. se calcula automáticamente (coste medio ponderado de los
pedidos de los últimos 30 días y, si no hay histórico, el precio de alta del artículo). Ver
`services/compras/precios_dinamicos.precio_referencia`. No crea tablas.
"""

VERSION = "0212"
DESCRIPCION = "articulos.precio_ref (Precio ref. manual; NULL = automático por histórico/alta)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "articulos"
_COLUMNA = "precio_ref"


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, _TABLA, _COLUMNA):
        cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {_COLUMNA} DECIMAL(10,2) DEFAULT NULL")


def revertir(cur):
    if _tiene_columna(cur, _TABLA, _COLUMNA):
        cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {_COLUMNA}")
