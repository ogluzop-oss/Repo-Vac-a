"""
Migracion 0099 — Historial de recomendaciones de SOMA (Fase 7). ADITIVA, idempotente, reversible.
Guarda qué RECOMENDÓ SOMA (iniciativas: riesgos/oportunidades/objetivos), cuándo, por qué, si el
usuario la aceptó/rechazó y el resultado — para mejorar futuras recomendaciones (aprendizaje lento de
prioridades). No conversaciones. Multiempresa/multiusuario.
"""

VERSION = "0099"
DESCRIPCION = "Historial de recomendaciones de SOMA: soma_recomendaciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("soma_recomendaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        clave VARCHAR(64) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'riesgo',
        dominio VARCHAR(40) DEFAULT NULL,
        titulo VARCHAR(200) DEFAULT NULL,
        prioridad VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        mensaje VARCHAR(500) DEFAULT NULL,
        por_que VARCHAR(500) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'PROPUESTA',
        resultado VARCHAR(255) DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        decidida DATETIME DEFAULT NULL,
        INDEX idx_soma_reco (id_empresa, usuario, tipo, estado, creada)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
