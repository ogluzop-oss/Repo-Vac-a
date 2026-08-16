"""
Migración 0201 — Política de cancelación de compras. ADITIVA, idempotente, reversible.

- `articulos.perecibilidad`: tipo de producto a efectos de la política de cancelación
  (no_perecedero | perecedero | bajo_pedido). Por defecto 'no_perecedero'.
- `compras_cancelaciones`: registro de cancelaciones (auditoría + strike system: contar cancelaciones
  reiteradas por empresa para limitar/suspender pujas).
"""

VERSION = "0201"
DESCRIPCION = "Cancelaciones: articulos.perecibilidad + tabla compras_cancelaciones (política + strikes)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA_ART = "articulos"
_COL = "perecibilidad"

_TABLAS = [
    ("compras_cancelaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_pedido BIGINT DEFAULT NULL,
        tipo_producto VARCHAR(16) NOT NULL DEFAULT 'no_perecedero',
        estado VARCHAR(16) NOT NULL DEFAULT 'pendiente',
        origen VARCHAR(16) NOT NULL DEFAULT 'compra_directa',
        recargo_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
        motivo VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_canc (id_empresa, creado_en)"""),
]


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, _TABLA_ART, _COL):
        cur.execute(f"ALTER TABLE {_TABLA_ART} ADD COLUMN {_COL} VARCHAR(16) NOT NULL "
                    f"DEFAULT 'no_perecedero'")
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
    if _tiene_columna(cur, _TABLA_ART, _COL):
        cur.execute(f"ALTER TABLE {_TABLA_ART} DROP COLUMN {_COL}")
