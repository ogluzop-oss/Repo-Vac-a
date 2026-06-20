"""
Migración 0018 — Control horario laboral (RD 8/2019). ADITIVA y reversible.

`rrhh_jornadas` (registro diario por empleado: entrada/salida/pausas/tiempo efectivo,
jornada planificada vs realizada, exceso/déficit) + `rrhh_pausas` (pausas de la jornada
por tipo). Integrado con el expediente (FK a rrhh_empleados). Multiempresa + multitienda.
No modifica `fichajes` (que se puede importar como puente). Trazabilidad (usuario/fechas).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0018"
DESCRIPCION = "Control horario laboral RD 8/2019 (rrhh_jornadas, rrhh_pausas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_jornadas (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_tienda           VARCHAR(64)  NOT NULL DEFAULT '',
            id_empleado         BIGINT       NOT NULL,
            fecha               DATE         NOT NULL,
            hora_entrada        DATETIME              DEFAULT NULL,
            hora_salida         DATETIME              DEFAULT NULL,
            pausa_segundos      INT          NOT NULL DEFAULT 0,
            tiempo_efectivo_min INT          NOT NULL DEFAULT 0,
            planificada_min     INT          NOT NULL DEFAULT 0,
            exceso_min          INT          NOT NULL DEFAULT 0,
            deficit_min         INT          NOT NULL DEFAULT 0,
            observaciones       VARCHAR(255)          DEFAULT NULL,
            usuario_registro    VARCHAR(120)          DEFAULT NULL,
            origen              VARCHAR(16)  NOT NULL DEFAULT 'manual',  -- manual|fichaje|import
            created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_jornada (id_empresa, id_empleado, fecha),
            INDEX idx_jor_empleado (id_empleado, fecha),
            INDEX idx_jor_empresa (id_empresa, fecha),
            INDEX idx_jor_tienda (id_tienda, fecha),
            CONSTRAINT fk_jor_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_pausas (
            id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa  CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_jornada  BIGINT       NOT NULL,
            tipo        VARCHAR(14)  NOT NULL DEFAULT 'descanso',  -- comida|descanso|medico|otros
            inicio      DATETIME              DEFAULT NULL,
            fin         DATETIME              DEFAULT NULL,
            segundos    INT          NOT NULL DEFAULT 0,
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pausa_jornada (id_jornada),
            CONSTRAINT fk_pausa_jornada FOREIGN KEY (id_jornada)
                REFERENCES rrhh_jornadas(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS rrhh_pausas")
    cur.execute("DROP TABLE IF EXISTS rrhh_jornadas")
