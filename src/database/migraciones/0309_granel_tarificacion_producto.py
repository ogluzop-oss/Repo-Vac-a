"""
Migración 0309 — Tipo de tarificación (Kg/Unidad) POR PRODUCTO a granel. ADITIVA, idempotente,
reversible.

Antes, si un producto se vendía por peso o por unidad lo decidía ÚNICAMENTE su familia
(`services.tpv.familias_granel._POR_UNIDAD` = Panes/Bollería venden por unidad, el resto por
peso) — un producto no podía apartarse del criterio de su familia (p. ej. un queso en lonchas
dentro de Lácteos, vendido por unidad, era imposible). `productos_granel.por_unidad` pasa esa
decisión a CADA producto; se sigue sugiriendo el valor de la familia como punto de partida al
crear uno nuevo, pero el superadministrador puede cambiarlo. El backfill preserva EXACTAMENTE el
comportamiento actual de todos los productos ya existentes (1 solo en Panes/Bollería, 0 el resto)
antes de habilitar la anulación caso por caso.
"""

VERSION = "0309"
DESCRIPCION = "productos_granel.por_unidad (tipo de tarificación Kg/Unidad por producto, no solo por familia)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE productos_granel ADD COLUMN IF NOT EXISTS "
                "por_unidad TINYINT(1) NOT NULL DEFAULT 0")
    cur.execute("UPDATE productos_granel SET por_unidad=1 WHERE categoria IN ('PANES', 'BOLLERIA')")


def revertir(cur):
    cur.execute("ALTER TABLE productos_granel DROP COLUMN IF EXISTS por_unidad")
