"""
Migración 0131 — Fase III · B5 Corporate Rules Engine. ADITIVA, idempotente, reversible.

Reglas de negocio SIN código: condiciones (JSON) → acciones (JSON). Motor universal reutilizable por
cualquier módulo. Multiempresa.
"""

VERSION = "0131"
DESCRIPCION = "Fase III · Rules Engine: rules (condiciones/acciones configurables)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("rules", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        evento VARCHAR(80) DEFAULT NULL,
        condiciones TEXT DEFAULT NULL,
        acciones TEXT DEFAULT NULL,
        prioridad INT NOT NULL DEFAULT 100,
        activo TINYINT NOT NULL DEFAULT 1,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_rules (id_empresa, evento, activo, prioridad)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
