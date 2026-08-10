"""
Migracion 0117 — Enriquecimiento de GMAO (Módulo 17). ADITIVA, idempotente, reversible.
Auditoría: GMAO ya cubre activos, planes de mantenimiento PREVENTIVO por calendario (job de Scheduler
genera OT), órdenes de trabajo con repuestos por kárdex y costes, y analítica (MTTR/MTBF, IA
predictiva). Se añade lo ausente: mantenimiento por USO/CONDICIÓN (medidores/horómetros con umbral
que disparan OT) y RONDAS/CHECKLISTS de inspección. Reutiliza `gmao.ordenes.crear_ot`. No duplica.
"""

VERSION = "0117"
DESCRIPCION = "GMAO: mantenimiento por uso (medidores) + rondas/checklists de inspección"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("gmao_medidores", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_activo INT NOT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'horas',
        lectura_actual DECIMAL(16,3) NOT NULL DEFAULT 0,
        umbral_preventivo DECIMAL(16,3) DEFAULT NULL,
        lectura_ultima_ot DECIMAL(16,3) NOT NULL DEFAULT 0,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_medidor (id_empresa, id_activo)"""),
    ("gmao_lecturas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_medidor INT NOT NULL,
        valor DECIMAL(16,3) NOT NULL,
        fecha DATE DEFAULT NULL,
        operario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_lectura (id_medidor, fecha)"""),
    ("gmao_checklists", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(40) NOT NULL,
        nombre VARCHAR(160) NOT NULL,
        items MEDIUMTEXT DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_checklist (id_empresa, codigo)"""),
    ("gmao_ronda_ejecuciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_checklist INT NOT NULL,
        id_activo INT DEFAULT NULL,
        resultados MEDIUMTEXT DEFAULT NULL,
        conforme TINYINT NOT NULL DEFAULT 1,
        operario VARCHAR(80) DEFAULT NULL,
        fecha DATE DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ronda (id_empresa, id_checklist, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
