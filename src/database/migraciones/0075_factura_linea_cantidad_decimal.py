"""
Migracion 0075 — Cantidad DECIMAL en lineas de factura (peso/granel). ADITIVA, reversible, idempotente.

Cambia facturas_cliente_lineas.cantidad de INT a DECIMAL(12,3) para representar pesos de
granel sin truncar (p. ej. 1.500 kg). Ampliacion segura (INT -> DECIMAL no pierde datos).
MODIFY es idempotente (re-ejecutar deja el mismo tipo). No toca venta_items ni el kardex.
"""

VERSION = "0075"
DESCRIPCION = "facturas_cliente_lineas.cantidad -> DECIMAL(12,3) (peso/granel sin truncar)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE facturas_cliente_lineas "
                "MODIFY COLUMN cantidad DECIMAL(12,3) NOT NULL DEFAULT 0")


def revertir(cur):
    cur.execute("ALTER TABLE facturas_cliente_lineas "
                "MODIFY COLUMN cantidad INT NOT NULL DEFAULT 0")
