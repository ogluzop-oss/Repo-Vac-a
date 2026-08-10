"""
Migracion 0069 — Marca de venta oculta en la vista de Facturas. ADITIVA, idempotente.

Cuando se elimina la factura de una venta desde la ventana 'Facturas', la venta se oculta
de ESA lista (no se borra la venta ni su kárdex/ticket). Columna NULLABLE/0 por defecto;
no afecta a otras consultas (p. ej. reimpresion de tickets).
"""

VERSION = "0069"
DESCRIPCION = "ventas.oculta_facturas (ocultar venta de la lista de Facturas tras borrar su factura)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS oculta_facturas TINYINT(1) DEFAULT 0")


def revertir(cur):
    cur.execute("ALTER TABLE ventas DROP COLUMN IF EXISTS oculta_facturas")
