"""
Migracion 0096 — Autonomia Supervisada / Ejecucion Controlada (Paquete Enterprise 10). ADITIVA,
idempotente, reversible. NO crea motores nuevos: el ExecutiveActionService coordina Workflow/BPM,
Gobierno Corporativo, AutomationService, Simulador, Gemelo Digital, IA y Agentes. Estas tablas SOLO
persisten los PLANES de ejecucion, sus ACCIONES (con estado previo para reversion) y el MODO de la
empresa. La IA propone, la organizacion decide, el sistema ejecuta solo lo autorizado.

  - exec_planes   : plan de ejecucion (origen, estado, modo, workflow de aprobacion, riesgo).
  - exec_acciones : acciones del plan por fase/orden (reversible/critica, estado previo, resultado).
  - exec_config   : modo de autonomia por empresa (MANUAL/ASISTIDA/SEMIAUTO/AVANZADA).

Multiempresa/multitienda/SaaS. Nada aqui ejecuta por si mismo: todo lo dispara el servicio bajo
autorizacion valida (Workflow + Gobierno) y queda auditado.
"""

VERSION = "0096"
DESCRIPCION = "Autonomia supervisada: exec_planes, exec_acciones, exec_config"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("exec_planes", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        origen VARCHAR(20) NOT NULL DEFAULT 'manual',
        origen_ref VARCHAR(80) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        descripcion VARCHAR(255) DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'BORRADOR',
        modo VARCHAR(16) NOT NULL DEFAULT 'ASISTIDA',
        confianza VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        riesgo VARCHAR(12) NOT NULL DEFAULT 'BAJO',
        workflow_entidad VARCHAR(40) DEFAULT NULL,
        workflow_ref VARCHAR(80) DEFAULT NULL,
        aprobado_por VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_exec_plan (id_empresa, estado, creado)"""),

    ("exec_acciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_plan BIGINT NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        fase INT NOT NULL DEFAULT 1,
        orden INT NOT NULL DEFAULT 1,
        codigo_accion VARCHAR(60) NOT NULL,
        titulo VARCHAR(160) DEFAULT NULL,
        params_json MEDIUMTEXT DEFAULT NULL,
        reversible TINYINT(1) NOT NULL DEFAULT 1,
        critica TINYINT(1) NOT NULL DEFAULT 0,
        estado VARCHAR(16) NOT NULL DEFAULT 'PENDIENTE',
        estado_previo_json MEDIUMTEXT DEFAULT NULL,
        resultado VARCHAR(255) DEFAULT NULL,
        ref_entidad VARCHAR(60) DEFAULT NULL,
        ref_id VARCHAR(80) DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        ejecutado DATETIME DEFAULT NULL,
        revertido DATETIME DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_exec_acc (id_plan, fase, orden),
        INDEX idx_exec_acc_emp (id_empresa, estado)"""),

    ("exec_config", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        modo VARCHAR(16) NOT NULL DEFAULT 'ASISTIDA',
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_exec_cfg (id_empresa)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
