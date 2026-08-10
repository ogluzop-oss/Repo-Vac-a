"""
Migración 0132 — Fase III · B4 Plugin SDK. ADITIVA, idempotente, reversible.

Registro de plugins instalados (manifest + estado). No ejecuta nada por sí misma. Multiempresa
(un plugin puede ser global —id_empresa NULL— o por empresa).
"""

VERSION = "0132"
DESCRIPCION = "Fase III · Plugin SDK: plugins_instalados"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("plugins_instalados", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        clave VARCHAR(80) NOT NULL,
        nombre VARCHAR(160) DEFAULT NULL,
        version VARCHAR(20) DEFAULT NULL,
        autor VARCHAR(120) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'instalado',
        manifest MEDIUMTEXT DEFAULT NULL,
        ruta VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        UNIQUE KEY uq_plugin (id_empresa, clave),
        INDEX idx_plugin (estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
