"""
Migracion 0098 — Mission Engine de SOMA (Fase 6). ADITIVA, idempotente, reversible. Persiste el
HISTORIAL de MISIONES (no conversaciones): objetivo, especialistas utilizados, resultado, estado,
aprobaciones y errores, más las tareas de cada misión (para reanudar/auditar/explicar). Reutiliza el
resto de la infraestructura (AgentManager, Workflow, Gobierno, Autonomía, Scheduler); estas tablas
solo guardan la traza de las misiones. Multiempresa/multiusuario.
"""

VERSION = "0098"
DESCRIPCION = "Mission Engine de SOMA: soma_misiones, soma_mision_tareas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("soma_misiones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        objetivo VARCHAR(255) NOT NULL,
        plantilla VARCHAR(60) DEFAULT NULL,
        prioridad VARCHAR(12) NOT NULL DEFAULT 'NORMAL',
        estado VARCHAR(24) NOT NULL DEFAULT 'PLANIFICADA',
        especialistas MEDIUMTEXT DEFAULT NULL,
        resultado MEDIUMTEXT DEFAULT NULL,
        aprobaciones INT NOT NULL DEFAULT 0,
        errores INT NOT NULL DEFAULT 0,
        duracion_ms BIGINT DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        cerrada DATETIME DEFAULT NULL,
        INDEX idx_soma_mis (id_empresa, estado, creada)"""),

    ("soma_mision_tareas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_mision BIGINT NOT NULL,
        clave VARCHAR(40) NOT NULL,
        orden INT NOT NULL DEFAULT 0,
        titulo VARCHAR(160) NOT NULL,
        dominio VARCHAR(40) DEFAULT NULL,
        deps VARCHAR(255) DEFAULT NULL,
        paralelo TINYINT(1) NOT NULL DEFAULT 1,
        estado VARCHAR(24) NOT NULL DEFAULT 'PENDIENTE',
        progreso INT NOT NULL DEFAULT 0,
        especialista VARCHAR(60) DEFAULT NULL,
        resultado MEDIUMTEXT DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizada DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_soma_mis_t (id_mision, orden)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
