"""
Migración 0323 — Portal de Incidencias / Helpdesk interno (petición explícita, módulo nuevo de
nivel superior en el menú principal). ADITIVA, idempotente, reversible.

Auditoría previa: el único motor de tickets existente (`services/sat/tickets.py`) está construido
de cabo a rabo alrededor de un cliente EXTERNO (SLA por contrato de cliente, encuesta de
satisfacción, portal de cliente) — reutilizarlo tal cual para incidencias INTERNAS de empleados
(equipamiento informático, soporte IT, consultas a RRHH) habría forzado conceptos que no aplican.
Se crea, por tanto, el único motor nuevo estrictamente necesario para esta pieza — sin tocar ni
duplicar `services/sat`.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0323"
DESCRIPCION = "Portal de Incidencias / Helpdesk interno (incidencias_internas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS incidencias_internas (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            codigo              VARCHAR(20)  NOT NULL,
            categoria           VARCHAR(20)  NOT NULL DEFAULT 'otro',
                                 -- equipo_informatico|soporte_tecnico|consulta_rrhh|otro
            asunto              VARCHAR(200) NOT NULL,
            descripcion         TEXT                  DEFAULT NULL,
            prioridad           VARCHAR(10)  NOT NULL DEFAULT 'media',  -- baja|media|alta
            estado              VARCHAR(12)  NOT NULL DEFAULT 'pendiente',
                                 -- pendiente|en_proceso|resuelto|cerrado
            id_usuario_solicitante INT       NOT NULL,
            nombre_solicitante  VARCHAR(120)          DEFAULT NULL,
            asignado_a          INT                   DEFAULT NULL,
            nombre_asignado     VARCHAR(120)          DEFAULT NULL,
            respuesta           TEXT                  DEFAULT NULL,
            fecha_creacion      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                             ON UPDATE CURRENT_TIMESTAMP,
            fecha_resolucion    DATETIME              DEFAULT NULL,
            UNIQUE KEY uq_inc_codigo (id_empresa, codigo),
            INDEX idx_inc_empresa_estado (id_empresa, estado),
            INDEX idx_inc_solicitante (id_empresa, id_usuario_solicitante)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS incidencias_internas_comentarios (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_incidencia   BIGINT       NOT NULL,
            autor           VARCHAR(120)          DEFAULT NULL,
            es_solicitante  TINYINT(1)   NOT NULL DEFAULT 0,
            cuerpo          TEXT         NOT NULL,
            fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_incc_incidencia (id_incidencia),
            CONSTRAINT fk_incc_incidencia FOREIGN KEY (id_incidencia)
                REFERENCES incidencias_internas(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS incidencias_internas_comentarios")
    cur.execute("DROP TABLE IF EXISTS incidencias_internas")
