"""
Migración 0179 — Importador maestro (ingesta de datos de empresa). ADITIVA, idempotente, reversible.

`import_trabajos` = registro/auditoría de cada importación (fichero, formato, filas ok/error).
`import_mapeos`  = perfiles de mapeo guardados por origen (re-importar sin re-mapear; se usa desde la Fase 2).
AISLAMIENTO por `id_empresa`. No toca datos existentes.
"""

VERSION = "0179"
DESCRIPCION = "Importador maestro: import_trabajos + import_mapeos (auditoría y perfiles de mapeo)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("import_trabajos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        fichero VARCHAR(255) DEFAULT NULL,
        entidad VARCHAR(32) NOT NULL DEFAULT 'productos',
        formato VARCHAR(16) DEFAULT NULL,
        filas_total INT NOT NULL DEFAULT 0,
        filas_ok INT NOT NULL DEFAULT 0,
        filas_error INT NOT NULL DEFAULT 0,
        estado VARCHAR(16) NOT NULL DEFAULT 'completado',
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_imp_trab (id_empresa, creado)"""),
    ("import_mapeos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        nombre VARCHAR(120) NOT NULL,
        entidad VARCHAR(32) NOT NULL DEFAULT 'productos',
        origen VARCHAR(255) DEFAULT NULL,
        mapeo TEXT NOT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_imp_map (id_empresa, entidad)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
