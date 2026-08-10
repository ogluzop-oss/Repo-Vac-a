"""
Migracion 0072 — IVA por linea en facturas_cliente_lineas (multi-IVA). ADITIVA, reversible, idempotente.

Persiste el tipo de IVA aplicado a cada linea de factura (origen: articulos.iva > IVA empresa).
Habilita el desglose multi-IVA en factura_impuestos. Columna NULLABLE: no afecta a filas
existentes ni a otras consultas. No toca venta_items ni el kardex.
"""

VERSION = "0072"
DESCRIPCION = "facturas_cliente_lineas.iva (tipo de IVA por linea, multi-IVA)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE facturas_cliente_lineas "
                "ADD COLUMN IF NOT EXISTS iva DECIMAL(5,2) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE facturas_cliente_lineas DROP COLUMN IF EXISTS iva")
