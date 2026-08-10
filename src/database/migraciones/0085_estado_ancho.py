"""
Migracion 0085 — Amplia facturas_cliente.estado a VARCHAR(20). ADITIVA, reversible, idempotente.

Los estados del workflow de aprobacion (FASE 4.5) como 'pendiente_aprobacion' (20 car.) no caben
en el VARCHAR(10) original (migr 0042). Ampliacion segura (no trunca datos). MODIFY idempotente.
"""

VERSION = "0085"
DESCRIPCION = "facturas_cliente.estado -> VARCHAR(20) (estados de aprobacion)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE facturas_cliente MODIFY COLUMN estado VARCHAR(20) NOT NULL DEFAULT 'borrador'")


def revertir(cur):
    cur.execute("ALTER TABLE facturas_cliente MODIFY COLUMN estado VARCHAR(10) NOT NULL DEFAULT 'borrador'")
