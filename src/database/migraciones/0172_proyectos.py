"""
Migración 0172 — Gestión de proyectos (Kanban/Gantt + rentabilidad). ADITIVA e IDEMPOTENTE.

  · `proyectos`        — proyecto con presupuesto, cliente/responsable, fechas y estado.
  · `proyecto_tareas`  — tareas con estado = columna Kanban (+ orden) y fechas para el cronograma (Gantt).
  · `proyecto_horas`   — imputación de horas (registro de horas × coste/hora) para la rentabilidad.
  · `proyecto_costes`  — costes extra (materiales/gastos) imputados al proyecto.
Rentabilidad = presupuesto − (Σ horas×coste_hora + Σ costes). No modifica datos existentes.
"""

VERSION = "0172"
DESCRIPCION = "Gestión de proyectos: proyectos + proyecto_tareas + proyecto_horas + proyecto_costes"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = {
    "proyectos": """
        CREATE TABLE IF NOT EXISTS proyectos (
            id                 INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa         VARCHAR(36)  DEFAULT NULL,
            nombre             VARCHAR(160) NOT NULL,
            descripcion        VARCHAR(500)          DEFAULT NULL,
            estado             VARCHAR(20)  NOT NULL DEFAULT 'planificado',
            id_cliente         INT                   DEFAULT NULL,
            responsable        VARCHAR(120)          DEFAULT NULL,
            fecha_inicio       DATE                  DEFAULT NULL,
            fecha_fin_prevista DATE                  DEFAULT NULL,
            presupuesto        DECIMAL(14,2) NOT NULL DEFAULT 0,
            coste_hora_defecto DECIMAL(10,2) NOT NULL DEFAULT 0,
            activo             TINYINT(1)   NOT NULL DEFAULT 1,
            creado             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_proy_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "proyecto_tareas": """
        CREATE TABLE IF NOT EXISTS proyecto_tareas (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa   VARCHAR(36)  DEFAULT NULL,
            id_proyecto  INT          NOT NULL,
            titulo       VARCHAR(200) NOT NULL,
            descripcion  VARCHAR(500)          DEFAULT NULL,
            estado       VARCHAR(20)  NOT NULL DEFAULT 'pendiente',
            orden        INT          NOT NULL DEFAULT 0,
            responsable  VARCHAR(120)          DEFAULT NULL,
            prioridad    VARCHAR(10)  NOT NULL DEFAULT 'media',
            fecha_inicio DATE                  DEFAULT NULL,
            fecha_fin    DATE                  DEFAULT NULL,
            creado       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_ptarea (id_empresa, id_proyecto, estado, orden)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "proyecto_horas": """
        CREATE TABLE IF NOT EXISTS proyecto_horas (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  DEFAULT NULL,
            id_proyecto INT          NOT NULL,
            id_tarea    INT                   DEFAULT NULL,
            usuario     VARCHAR(120)          DEFAULT NULL,
            fecha       DATE                  DEFAULT NULL,
            horas       DECIMAL(8,2) NOT NULL DEFAULT 0,
            coste_hora  DECIMAL(10,2) NOT NULL DEFAULT 0,
            descripcion VARCHAR(300)          DEFAULT NULL,
            creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_phoras (id_empresa, id_proyecto)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "proyecto_costes": """
        CREATE TABLE IF NOT EXISTS proyecto_costes (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  DEFAULT NULL,
            id_proyecto INT          NOT NULL,
            concepto    VARCHAR(200) NOT NULL,
            importe     DECIMAL(12,2) NOT NULL DEFAULT 0,
            tipo        VARCHAR(20)  NOT NULL DEFAULT 'gasto',
            fecha       DATE                  DEFAULT NULL,
            creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pcostes (id_empresa, id_proyecto)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


def aplicar(cur):
    for ddl in _TABLAS.values():
        cur.execute(ddl)


def revertir(cur):
    for t in ("proyecto_costes", "proyecto_horas", "proyecto_tareas", "proyectos"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
