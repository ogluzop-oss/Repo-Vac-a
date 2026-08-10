"""
Migracion 0100 — Memoria EMPRESARIAL a largo plazo de SOMA (Fase 8). ADITIVA, idempotente, reversible.
Guarda SOLO conocimiento útil de cómo trabaja la empresa (decisiones, preferencias, hábitos, patrones,
configuraciones, iniciativas realizadas, objetivos completados) — NUNCA conversaciones. Es por EMPRESA
(no por usuario, a diferencia de soma_memoria de la Fase 5). Aprendizaje lento (contador) y reversible
(activo=0 = olvidado).
"""

VERSION = "0100"
DESCRIPCION = "Memoria empresarial de SOMA a largo plazo: soma_empresa_conocimiento"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("soma_empresa_conocimiento", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        tipo VARCHAR(24) NOT NULL,
        clave VARCHAR(140) NOT NULL,
        valor VARCHAR(400) DEFAULT NULL,
        contador INT NOT NULL DEFAULT 1,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_soma_conoc (id_empresa, tipo, clave),
        INDEX idx_soma_conoc (id_empresa, tipo, activo, contador)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
