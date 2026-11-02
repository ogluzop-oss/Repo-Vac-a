"""
Migración 0315 — `articulos.genero`. ADITIVA, idempotente, reversible.

Nuevo filtro de búsqueda de artículos ("Filtros": talla/color/precio/género — Retail/Textil/
Supermarket, ver `gui/components/completer_articulos.py`). Talla/color ya existían
(`producto_variantes`, migr. del módulo de variantes textil); el segmento de público objetivo
(Hombre/Mujer/Niño/Niña/Unisex) no estaba modelado en ningún sitio — se añade como columna libre
(no ENUM, para no acoplar la validación a la BD) en `articulos`, con el mismo combo cerrado que la
GUI ya usa para limitar los valores reales introducidos.
"""

VERSION = "0315"
DESCRIPCION = "articulos.genero (segmento de público objetivo, para el filtro de búsqueda)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS genero VARCHAR(10) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE articulos DROP COLUMN IF EXISTS genero")
