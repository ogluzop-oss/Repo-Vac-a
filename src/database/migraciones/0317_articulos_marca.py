"""
Migración 0317 — `articulos.marca`. ADITIVA, idempotente, reversible.

Soporte de la detección de duplicados en Alta artículo / pedidos a proveedor (petición explícita):
"coincidencia EXACTA simultánea de 4 parámetros (Nombre, Talla, Marca, Color)". Nombre ya existe;
Talla/Color ya existen en `producto_variantes` (módulo de variantes Textil); "Marca" no estaba
modelada en ningún sitio del catálogo base (confirmado por auditoría) — se añade como columna
libre (no ENUM/FK, mismo criterio que `articulos.genero` en la migración 0315) para no acoplar la
validación a una tabla de marcas que no existe. Mismo campo sirve para el equivalente sectorial
que pida cada proveedor (p. ej. un proveedor agrícola usa "variedad" en vez de "marca") — es la
GUI/portal quien decide la ETIQUETA mostrada, no la columna.
"""

VERSION = "0317"
DESCRIPCION = "articulos.marca (para la detección de duplicados Nombre+Talla+Marca+Color)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS marca VARCHAR(100) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE articulos DROP COLUMN IF EXISTS marca")
