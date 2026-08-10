"""
Migracion 0068 — Domicilio fiscal del cliente. ADITIVA, idempotente, reversible.

Anade a `clientes` los campos planos de direccion fiscal (cp, poblacion, provincia, pais)
para poder emitir facturas completas a su nombre. No toca datos existentes ni logica.
"""

VERSION = "0068"
DESCRIPCION = "Clientes: domicilio fiscal (cp, poblacion, provincia, pais) para facturacion"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("cp", "VARCHAR(12) DEFAULT NULL"),
    ("poblacion", "VARCHAR(120) DEFAULT NULL"),
    ("provincia", "VARCHAR(120) DEFAULT NULL"),
    ("pais", "VARCHAR(80) DEFAULT NULL"),
]


def aplicar(cur):
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE clientes ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE clientes DROP COLUMN IF EXISTS {col}")
