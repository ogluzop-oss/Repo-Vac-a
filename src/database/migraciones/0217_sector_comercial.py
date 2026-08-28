"""
Migración 0217 — Sector Comercial (Smart Suppliers · Fase A). ADITIVA, idempotente, reversible.

Introduce el catálogo de sectores comerciales y su grafo de compatibilidad (usado para el match
Empresa↔Proveedor del catálogo B2B), y añade `sector_id` a `empresas` y `proveedores`. No toca ninguna
columna ni tabla existente.
"""

VERSION = "0217"
DESCRIPCION = "Smart Suppliers: catálogo de sectores comerciales + sector_id en empresas/proveedores"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("sectores_comerciales", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        UNIQUE KEY uq_sector_codigo (codigo)"""),
    ("sectores_compatibles", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        sector_id INT NOT NULL,
        sector_compatible_id INT NOT NULL,
        UNIQUE KEY uq_sector_compat (sector_id, sector_compatible_id),
        INDEX idx_sc_sector (sector_id)"""),
]

_EMPRESAS = [("sector_id", "INT DEFAULT NULL")]
_PROVEEDORES = [("sector_id", "INT DEFAULT NULL")]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for col, ddl in _EMPRESAS:
        cur.execute(f"ALTER TABLE empresas ADD COLUMN IF NOT EXISTS {col} {ddl}")
    for col, ddl in _PROVEEDORES:
        cur.execute(f"ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _PROVEEDORES:
        cur.execute(f"ALTER TABLE proveedores DROP COLUMN IF EXISTS {col}")
    for col, _ in _EMPRESAS:
        cur.execute(f"ALTER TABLE empresas DROP COLUMN IF EXISTS {col}")
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
