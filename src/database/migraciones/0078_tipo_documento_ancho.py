"""
Migracion 0078 — Amplia facturas_cliente.tipo_documento a VARCHAR(20). ADITIVA, reversible, idempotente.

El framework de tipos (FASE 3.3) usa claves como 'intracomunitaria' (16 car.) que no caben en el
VARCHAR(15) original (migr 0074). Ampliacion segura (no trunca datos). MODIFY es idempotente.
"""

VERSION = "0078"
DESCRIPCION = "facturas_cliente.tipo_documento -> VARCHAR(20) (tipos largos: intracomunitaria)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE facturas_cliente "
                "MODIFY COLUMN tipo_documento VARCHAR(20) NOT NULL DEFAULT 'factura'")


def revertir(cur):
    cur.execute("ALTER TABLE facturas_cliente "
                "MODIFY COLUMN tipo_documento VARCHAR(15) NOT NULL DEFAULT 'factura'")
