"""
Migracion 0097 — Memoria persistente de SOMA (Fase 5). ADITIVA, idempotente, reversible. Almacena
SOLO información ÚTIL y aprendida lentamente (preferencias, hábitos, módulos/empresas/tiendas
frecuentes, idioma, configuraciones favoritas, decisiones repetitivas) — nunca conversaciones
completas. Es la única tabla propia de SOMA; no duplica la memoria de sesión (copilot.memoria).
Multiempresa/multiusuario.
"""

VERSION = "0097"
DESCRIPCION = "Memoria persistente de SOMA: soma_memoria"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("soma_memoria", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        usuario VARCHAR(80) NOT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'preferencia',
        clave VARCHAR(120) NOT NULL,
        valor VARCHAR(255) DEFAULT NULL,
        contador INT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_soma_mem (id_empresa, usuario, tipo, clave),
        INDEX idx_soma_mem (usuario, tipo, contador)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
