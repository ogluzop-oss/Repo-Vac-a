"""
Migración 0320 — "Artículo complementario" / "Artículo promocional" (petición explícita, para
contar "Ventas cruzadas" y "Ventas promocionales" en el Resumen de Ventas). ADITIVA, idempotente,
reversible. Auditoría previa: no existía ningún concepto de "complementario"/"promocional" en
`articulos` (distinto de `promo_activa`/`precio_promo`, que es el precio de oferta/tachado del
Catálogo Web — un concepto de PRECIO, no de categoría comercial del artículo).
"""

VERSION = "0320"
DESCRIPCION = "articulos.es_complementario + articulos.es_promocional"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS es_complementario "
               "TINYINT(1) NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS es_promocional "
               "TINYINT(1) NOT NULL DEFAULT 0")


def revertir(cur):
    cur.execute("ALTER TABLE articulos DROP COLUMN IF EXISTS es_complementario")
    cur.execute("ALTER TABLE articulos DROP COLUMN IF EXISTS es_promocional")
