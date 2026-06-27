"""
Migración 0053 — Retención IRPF en facturas de compra (FASE AEAT-3). ADITIVA, idempotente.

Añade `retencion_pct` y `retencion_importe` a `compras_facturas` para capturar la retención
de profesionales. Por defecto 0 → las facturas existentes y las sin retención no cambian de
comportamiento (total = base + iva). Reversible.
"""

VERSION = "0053"
DESCRIPCION = "Retención IRPF en compras_facturas (retencion_pct/retencion_importe)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE compras_facturas ADD COLUMN IF NOT EXISTS "
                "retencion_pct DECIMAL(5,2) NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE compras_facturas ADD COLUMN IF NOT EXISTS "
                "retencion_importe DECIMAL(14,2) NOT NULL DEFAULT 0")


def revertir(cur):
    cur.execute("ALTER TABLE compras_facturas DROP COLUMN IF EXISTS retencion_importe")
    cur.execute("ALTER TABLE compras_facturas DROP COLUMN IF EXISTS retencion_pct")
