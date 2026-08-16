"""
Migración 0200 — Lonja: subasta profesional (precio de reserva + incremento mínimo). ADITIVA,
idempotente, reversible.

Añade a `lonja_listados` dos columnas para profesionalizar las subastas:
- `precio_reserva`: precio mínimo por debajo del cual el lote NO se adjudica (queda 'desierta').
- `incremento_minimo`: cada puja debe superar a la mejor en al menos este importe.
La DURACIÓN de la subasta ya se controla con `fecha_limite` (migr 0199) + el job de cierre.
"""

VERSION = "0200"
DESCRIPCION = "lonja_listados: precio_reserva + incremento_minimo (subasta profesional)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "lonja_listados"
_COLS = (("precio_reserva", "DECIMAL(14,4) DEFAULT NULL"),
         ("incremento_minimo", "DECIMAL(14,4) NOT NULL DEFAULT 0"))


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _COLS:
        if not _tiene_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {col} {ddl}")


def revertir(cur):
    for col, _ in reversed(_COLS):
        if _tiene_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {col}")
