"""
Migración 0028 — Proveedores profesionales (CMP.1). ADITIVA, reversible, idempotente.

Amplía `proveedores` con condiciones comerciales, datos bancarios/fiscales, homologación
y bloqueo. No elimina nada; conserva el `estado` existente.
"""

VERSION = "0028"
DESCRIPCION = "Proveedores PRO: condiciones comerciales + bancarios + homologación/bloqueo"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("plazo_pago", "INT NOT NULL DEFAULT 0"),            # días
    ("lead_time_dias", "INT NOT NULL DEFAULT 0"),
    ("descuento", "DECIMAL(5,2) NOT NULL DEFAULT 0"),    # % global
    ("rappel", "DECIMAL(5,2) NOT NULL DEFAULT 0"),       # % rappel
    ("divisa", "VARCHAR(3) NOT NULL DEFAULT 'EUR'"),
    ("iban", "VARCHAR(34) DEFAULT NULL"),
    ("irpf", "DECIMAL(5,2) NOT NULL DEFAULT 0"),
    ("homologado", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("bloqueado", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("categoria", "VARCHAR(50) DEFAULT NULL"),
]


def aplicar(cur):
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS {col} {ddl}")
    cur.execute("ALTER TABLE proveedores ADD INDEX IF NOT EXISTS idx_prov_bloqueo "
                "(id_empresa, bloqueado)")


def revertir(cur):
    cur.execute("ALTER TABLE proveedores DROP INDEX IF EXISTS idx_prov_bloqueo")
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE proveedores DROP COLUMN IF EXISTS {col}")
