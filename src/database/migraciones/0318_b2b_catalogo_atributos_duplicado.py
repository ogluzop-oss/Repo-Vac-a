"""
Migración 0318 — `b2b_catalogo.talla/marca/color`. ADITIVA, idempotente, reversible.

Soporte de la detección de duplicados antes de un pedido a proveedor (petición explícita):
coincidencia EXACTA simultánea de Nombre + Talla + Marca + Color (adaptable por sector: p. ej. un
proveedor agrícola usaría estos mismos campos libres para variedad/calibre en vez de talla/marca —
es la GUI/portal quien decide la ETIQUETA mostrada, no la columna, mismo criterio que
`articulos.marca`, migración 0317). `b2b_catalogo` (auditoría previa) no tenía ningún campo de
atributo más allá de nombre/unidad/MOQ/precio — se añaden como opcionales, sin romper ninguna fila
ni formulario existente.
"""

VERSION = "0318"
DESCRIPCION = "b2b_catalogo.talla/marca/color (para la detección de duplicados en el pedido)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE b2b_catalogo ADD COLUMN IF NOT EXISTS talla VARCHAR(50) DEFAULT NULL")
    cur.execute("ALTER TABLE b2b_catalogo ADD COLUMN IF NOT EXISTS marca VARCHAR(100) DEFAULT NULL")
    cur.execute("ALTER TABLE b2b_catalogo ADD COLUMN IF NOT EXISTS color VARCHAR(50) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE b2b_catalogo DROP COLUMN IF EXISTS talla")
    cur.execute("ALTER TABLE b2b_catalogo DROP COLUMN IF EXISTS marca")
    cur.execute("ALTER TABLE b2b_catalogo DROP COLUMN IF EXISTS color")
