"""
Migración 0211 — Reestructuración Pedidos/Artículos. ADITIVA, idempotente, reversible.

- `compras_pedidos.uuid`         : UUID único de pedido (trazabilidad QR, se fija al tramitar).
- `compras_pedidos_lineas.pvp_sugerido` : PVP dinámico calculado EN LA TRAMITACIÓN (coste × margen).
- `articulos.unidad`             : unidad de medida (kg/unidad/caja/saco…) para el Alta Rápida + EAN-13.

Reutiliza tablas PERMANENTES existentes (0009 compras_pedidos/lineas, articulos). No crea tablas.
"""

VERSION = "0211"
DESCRIPCION = "compras_pedidos.uuid + compras_pedidos_lineas.pvp_sugerido + articulos.unidad"
REVERSIBLE = True
REQUIERE_BACKUP = False

# (tabla, columna, definición)
_COLUMNAS = [
    ("compras_pedidos", "uuid", "CHAR(36) DEFAULT NULL"),
    ("compras_pedidos_lineas", "pvp_sugerido", "DECIMAL(10,2) DEFAULT NULL"),
    ("articulos", "unidad", "VARCHAR(16) DEFAULT NULL"),
]


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for tabla, col, definicion in _COLUMNAS:
        if not _tiene_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for tabla, col, _ in reversed(_COLUMNAS):
        if _tiene_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
