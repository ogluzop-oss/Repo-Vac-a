"""Migración 0258 — Trazabilidad por lote obligatoria (Punto 3, lotes/FEFO). ADITIVA,
idempotente, reversible.

Añade `articulos.requiere_lote TINYINT(1) DEFAULT 0`: flag por artículo que, cuando está
activo, exige lote/fecha de caducidad en la recepción (en vez de mostrarlos como opcionales).
El motor de lotes/FEFO (`db/lotes.py`) ya existe íntegro (migración 0022) y ya está conectado
a la salida de stock normal (`db/salida_stock.py`) y a la recepción de compra B2B
(`db/compras.py::recibir`, ya opcionalmente consciente de lote/caducidad); esta columna es el
único dato maestro que faltaba para poder EXIGIR lote en vez de ofrecerlo como opcional.

Retrocompatible: por defecto 0 (opcional) para todo artículo existente — ningún flujo de
recepción actual queda bloqueado por este cambio.
"""

VERSION = "0259"
DESCRIPCION = "Trazabilidad por lote obligatoria: articulos.requiere_lote"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLUMNAS = [
    ("articulos", "requiere_lote", "TINYINT(1) NOT NULL DEFAULT 0"),
]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for tabla, col, definicion in _COLUMNAS:
        if not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for tabla, col, _ in reversed(_COLUMNAS):
        if _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
