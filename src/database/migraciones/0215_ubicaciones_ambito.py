"""
Migración 0215 — Ámbito y planta de las ubicaciones. ADITIVA, idempotente, reversible.

Añade a `ubicaciones` dos columnas para conectar las asignaciones (Asignar Ubicación Lineal/Almacén) con
las coordenadas de las estanterías (Gestión Estructura) y separarlas por ámbito/plano:

- `ambito VARCHAR(10)`  → 'LINEAL' (planos de local) o 'ALMACEN' (planos de almacén). Distingue a qué mundo
  pertenece una estantería/pasillo, para filtrar el selector de Gestión Estructura por el tipo del plano.
- `planta_index INT`    → planta a la que pertenece el nodo de estantería (para futuros filtros por planta).

No crea tablas. No toca datos existentes.
"""

VERSION = "0215"
DESCRIPCION = "ubicaciones.ambito ('LINEAL'/'ALMACEN') + ubicaciones.planta_index (conexión asignación↔coords)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "ubicaciones"
_COLS = (
    ("ambito", "VARCHAR(10) DEFAULT NULL"),
    ("planta_index", "INT DEFAULT NULL"),
)


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, tipo in _COLS:
        if not _tiene_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {col} {tipo}")


def revertir(cur):
    for col, _ in _COLS:
        if _tiene_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {col}")
