"""
Migración 0210 — Ficha del proveedor: campos comerciales/contacto adicionales. ADITIVA, idempotente,
reversible.

Amplía la tabla PERMANENTE `proveedores` (migr 0008) con los campos que faltaban para la nueva "Ficha
del proveedor" (Datos Generales + Condiciones Comerciales). Reutiliza los ya existentes cuando los hay
(`plazo_pago` = días de pago, `lead_time_dias` = días de entrega, `iban` = IBAN de abono, `divisa`,
`descuento`, `rappel`, `estado`, `nombre_comercial`, `direccion_fiscal`, `observaciones`). Solo se añaden
los que NO existían. No crea tablas ni toca otros módulos.
"""

VERSION = "0210"
DESCRIPCION = "proveedores: web, persona_contacto, forma_pago, pedido_minimo (Ficha del proveedor)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "proveedores"

# (columna, definición)
_COLUMNAS = [
    ("web", "VARCHAR(255) DEFAULT NULL"),
    ("persona_contacto", "VARCHAR(150) DEFAULT NULL"),
    ("forma_pago", "VARCHAR(40) DEFAULT NULL"),
    ("pedido_minimo", "DECIMAL(12,2) DEFAULT NULL"),
]


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, definicion in _COLUMNAS:
        if not _tiene_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for col, _ in reversed(_COLUMNAS):
        if _tiene_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {col}")
