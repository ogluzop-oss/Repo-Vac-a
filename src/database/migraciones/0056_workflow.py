"""
Migración 0056 — Workflow / BPM / Aprobaciones. ADITIVA, idempotente, reversible.

Capa transversal de circuitos de aprobación configurables por empresa. NO toca ninguna tabla
existente ni los estados de los dominios: el workflow es una capa ADICIONAL. Tablas:
definiciones, pasos, reglas (condiciones p.ej. por importe), instancias, tareas, log y
delegaciones. Multiempresa (id_empresa en definiciones/instancias).
"""

VERSION = "0056"
DESCRIPCION = "Workflow/BPM: definiciones, pasos, reglas, instancias, tareas, log, delegaciones"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wf_definiciones (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            codigo      VARCHAR(40)  NOT NULL,
            nombre      VARCHAR(120) NOT NULL,
            descripcion VARCHAR(255) DEFAULT NULL,
            entidad     VARCHAR(40)  NOT NULL,
            version     INT          NOT NULL DEFAULT 1,
            activo      TINYINT      NOT NULL DEFAULT 1,
            fecha_creacion DATETIME  DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_wfdef (id_empresa, codigo, version),
            INDEX idx_wfdef_ent (id_empresa, entidad, activo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wf_pasos (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_definicion INT        NOT NULL,
            orden       INT          NOT NULL,
            nombre      VARCHAR(120) NOT NULL,
            tipo_paso   VARCHAR(20)  NOT NULL DEFAULT 'aprobacion',
            permiso_requerido VARCHAR(80) DEFAULT NULL,
            rol_requerido     VARCHAR(40) DEFAULT NULL,
            grupo_requerido   VARCHAR(40) DEFAULT NULL,
            usuarios_minimos  INT       NOT NULL DEFAULT 1,
            obligatorio TINYINT      NOT NULL DEFAULT 1,
            sla_horas   INT          DEFAULT NULL,
            INDEX idx_wfpaso (id_definicion, orden)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wf_reglas (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_definicion INT        NOT NULL,
            id_paso     INT          DEFAULT NULL,
            condicion   VARCHAR(40)  NOT NULL,
            operador    VARCHAR(8)   NOT NULL DEFAULT '>=',
            valor       VARCHAR(64)  DEFAULT NULL,
            accion      VARCHAR(40)  NOT NULL DEFAULT 'activar_paso',
            INDEX idx_wfregla (id_definicion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wf_instancias (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            id_definicion INT        NOT NULL,
            entidad     VARCHAR(40)  NOT NULL,
            entidad_id  VARCHAR(64)  NOT NULL,
            estado      VARCHAR(14)  NOT NULL DEFAULT 'EN_CURSO',
            paso_actual INT          DEFAULT NULL,
            contexto    TEXT         DEFAULT NULL,
            fecha_inicio DATETIME    DEFAULT CURRENT_TIMESTAMP,
            fecha_fin   DATETIME     DEFAULT NULL,
            UNIQUE KEY uq_wfinst (id_empresa, entidad, entidad_id, id_definicion),
            INDEX idx_wfinst (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wf_tareas (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            id_instancia INT         NOT NULL,
            id_paso     INT          NOT NULL,
            estado      VARCHAR(12)  NOT NULL DEFAULT 'PENDIENTE',
            asignado_usuario INT     DEFAULT NULL,
            asignado_rol     VARCHAR(40) DEFAULT NULL,
            asignado_grupo   VARCHAR(40) DEFAULT NULL,
            permiso_requerido VARCHAR(80) DEFAULT NULL,
            aprobado_por INT         DEFAULT NULL,
            comentario  VARCHAR(255) DEFAULT NULL,
            fecha_creacion DATETIME  DEFAULT CURRENT_TIMESTAMP,
            fecha_resolucion DATETIME DEFAULT NULL,
            INDEX idx_wftarea (id_empresa, estado),
            INDEX idx_wftarea_inst (id_instancia, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wf_log (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            id_instancia INT         NOT NULL,
            accion      VARCHAR(24)  NOT NULL,
            usuario     INT          DEFAULT NULL,
            fecha       DATETIME     DEFAULT CURRENT_TIMESTAMP,
            detalle     VARCHAR(255) DEFAULT NULL,
            INDEX idx_wflog (id_instancia)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wf_delegaciones (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  NOT NULL,
            usuario_origen  INT      NOT NULL,
            usuario_destino INT      NOT NULL,
            fecha_inicio DATE        DEFAULT NULL,
            fecha_fin   DATE         DEFAULT NULL,
            activa      TINYINT      NOT NULL DEFAULT 1,
            INDEX idx_wfdeleg (id_empresa, usuario_origen, activa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    for t in ("wf_delegaciones", "wf_log", "wf_tareas", "wf_instancias",
              "wf_reglas", "wf_pasos", "wf_definiciones"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
