"""
Migración 0307 — Etiqueta personalizada de familia a granel. ADITIVA, idempotente, reversible.

El superadministrador puede ahora editar también el TEXTO de cada una de las 9 tarjetas de
familia (antes solo la imagen, migración 0306), desde el nuevo botón único "Editar familias".
`etiqueta_personalizada` NULL = se sigue mostrando la etiqueta por defecto de
`services.tpv.familias_granel` (p. ej. "Fruta") — nunca se pierde el texto original.
"""

VERSION = "0307"
DESCRIPCION = "familias_granel_imagenes.etiqueta_personalizada (texto editable de cada familia)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE familias_granel_imagenes "
                "ADD COLUMN IF NOT EXISTS etiqueta_personalizada VARCHAR(100) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE familias_granel_imagenes DROP COLUMN IF EXISTS etiqueta_personalizada")
