"""
Migracion 0086 — Anade mermas.exportada (TINYINT) para distinguir las mermas
pendientes de exportar a Excel de las ya exportadas. ADITIVA, reversible, idempotente.

La pestana "Exportar mermas" lista los articulos mermados que AUN no se han
exportado; tras exportar, se marcan exportada=1 y la tabla se vacia.
"""

VERSION = "0086"
DESCRIPCION = "mermas.exportada TINYINT(1) DEFAULT 0 (pendientes de exportar)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE mermas ADD COLUMN IF NOT EXISTS exportada TINYINT(1) NOT NULL DEFAULT 0"
    )


def revertir(cur):
    cur.execute("ALTER TABLE mermas DROP COLUMN IF EXISTS exportada")
