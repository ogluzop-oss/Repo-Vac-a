"""
Migración 0232 — Fecha límite de devolución CONGELADA por venta.

Hasta ahora el plazo de devolución se recalculaba en caliente con la configuración VIGENTE en el
momento de la consulta (`config_ticket.devol_dias`), así que si la empresa cambiaba el plazo (p. ej.
lo amplía por Navidad), el plazo de TODOS los tickets ya emitidos cambiaba retroactivamente con él —
un ticket entregado al cliente bajo una política de 30 días podía pasar a tener 60 sin que nada en el
ticket lo reflejase. Esta columna congela la fecha límite en el momento de la venta (fecha_venta +
devol_dias vigente ENTONCES), que es lo que se imprime en el ticket: cada venta conserva su propio
plazo para siempre, tal y como se le comunicó al cliente. Las ventas anteriores a esta migración quedan
con `NULL` (se degrada al cálculo dinámico anterior, ver `refund_service.validar_plazo`). ADITIVA,
idempotente, reversible.
"""

VERSION = "0232"
DESCRIPCION = "Columna ventas.fecha_limite_devolucion (plazo de devolución congelado por venta)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("SHOW COLUMNS FROM ventas LIKE 'fecha_limite_devolucion'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE ventas ADD COLUMN fecha_limite_devolucion DATETIME NULL")


def revertir(cur):
    cur.execute("SHOW COLUMNS FROM ventas LIKE 'fecha_limite_devolucion'")
    if cur.fetchone():
        cur.execute("ALTER TABLE ventas DROP COLUMN fecha_limite_devolucion")
