"""
Migración 0136 — Fase V · Bloque 4 Business Process Designer. ADITIVA, idempotente, reversible.

Persistencia del DISEÑO visual de procesos (borrador/publicado + versionado + rollback). El diseño
se COMPILA al Workflow Engine existente; NO es un motor nuevo. Multiempresa.
"""

VERSION = "0136"
DESCRIPCION = "Fase V · Business Process Designer: procesos y versiones de diseño"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("bpd_procesos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        clave VARCHAR(80) NOT NULL,
        nombre VARCHAR(160) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'borrador',   -- borrador|publicado
        version_actual INT NOT NULL DEFAULT 0,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        UNIQUE KEY uq_proc (id_empresa, clave),
        INDEX idx_proc (estado)"""),
    ("bpd_versiones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_proceso BIGINT NOT NULL,
        id_empresa CHAR(36) DEFAULT NULL,
        version INT NOT NULL,
        definicion MEDIUMTEXT DEFAULT NULL,               -- JSON del diseño (nodos/aristas)
        estado VARCHAR(16) NOT NULL DEFAULT 'borrador',   -- borrador|publicado
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ver (id_proceso, version)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
