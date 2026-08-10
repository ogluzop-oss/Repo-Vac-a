"""
Migración 0130 — Fase III · B3 Enterprise Scheduler. ADITIVA, idempotente, reversible.

Planificaciones persistentes (inmediata/diferida/diaria/…/cron) con prioridad, reintentos, estado y
próxima ejecución. No sustituye el catálogo de jobs existente: lo complementa con programación real.
Multiempresa.
"""

VERSION = "0130"
DESCRIPCION = "Fase III · Scheduler: scheduler_schedules + scheduler_ejecuciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("scheduler_schedules", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        job VARCHAR(80) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'cron',
        expresion VARCHAR(120) DEFAULT NULL,
        params TEXT DEFAULT NULL,
        prioridad VARCHAR(12) NOT NULL DEFAULT 'normal',
        estado VARCHAR(16) NOT NULL DEFAULT 'activo',
        max_reintentos INT NOT NULL DEFAULT 0,
        proxima_ejecucion DATETIME DEFAULT NULL,
        ultima_ejecucion DATETIME DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_sch (id_empresa, estado, proxima_ejecucion)"""),
    ("scheduler_ejecuciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_schedule BIGINT NOT NULL,
        id_empresa CHAR(36) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'ok',
        intento INT NOT NULL DEFAULT 1,
        detalle VARCHAR(255) DEFAULT NULL,
        duracion_ms INT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_sch_ej (id_schedule, creado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
