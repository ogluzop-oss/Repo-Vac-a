"""
Migración 0245 — mermas.origen_stock: recuerda de qué origen (STOCK LINEAL / STOCK ALMACÉN) se
descontó cada merma al registrarla. ADITIVA, reversible.

Antes, modificar/eliminar una merma volvía a PREGUNTAR "¿de dónde descontar/devolver el stock?" —
información que ya se había capturado al registrar la merma y que el empleado, en la práctica, no
recuerda al volver más tarde a corregir o borrar el registro. Persistiendo el origen elegido en el
propio registro, modificar/eliminar puede reutilizarlo automáticamente sin volver a preguntar.
"""

VERSION = "0245"
DESCRIPCION = "mermas.origen_stock VARCHAR(20) NULL (STOCK LINEAL / STOCK ALMACÉN elegido al registrar)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE mermas ADD COLUMN IF NOT EXISTS origen_stock VARCHAR(20) DEFAULT NULL"
    )


def revertir(cur):
    cur.execute("ALTER TABLE mermas DROP COLUMN IF EXISTS origen_stock")
