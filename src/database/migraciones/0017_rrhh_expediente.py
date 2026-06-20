"""
Migración 0017 — Expediente laboral del trabajador (F4.1.2). ADITIVA y reversible.

Núcleo de persistencia RRHH: `rrhh_empleados` (ficha/expediente) + historiales
contractual (`rrhh_contratos`), salarial (`rrhh_nominas`), de vacaciones
(`rrhh_vacaciones`), de ausencias (`rrhh_ausencias`) y vínculo documental genérico
(`rrhh_documentos`). Multiempresa (`id_empresa`) y preparado para multi-tienda
(`id_tienda`). No modifica ninguna tabla existente.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0017"
DESCRIPCION = "Expediente laboral RRHH (rrhh_empleados + historiales)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_empleados (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_tienda       VARCHAR(64)  NOT NULL DEFAULT '',
            id_usuario      INT                   DEFAULT NULL,
            -- Identificación
            nombre          VARCHAR(120) NOT NULL,
            apellidos       VARCHAR(180)          DEFAULT NULL,
            sexo            VARCHAR(10)           DEFAULT NULL,
            fecha_nacimiento DATE                 DEFAULT NULL,
            nacionalidad    VARCHAR(60)           DEFAULT NULL,
            nif             VARCHAR(20)  NOT NULL,
            num_ss          VARCHAR(20)           DEFAULT NULL,
            -- Contacto
            direccion       VARCHAR(255)          DEFAULT NULL,
            municipio       VARCHAR(120)          DEFAULT NULL,
            provincia       VARCHAR(120)          DEFAULT NULL,
            cp              VARCHAR(10)           DEFAULT NULL,
            pais            VARCHAR(60)           DEFAULT 'ESPAÑA',
            telefono        VARCHAR(30)           DEFAULT NULL,
            email           VARCHAR(160)          DEFAULT NULL,
            -- Laboral
            id_centro       CHAR(36)              DEFAULT NULL,
            categoria       VARCHAR(120)          DEFAULT NULL,
            grupo_prof      VARCHAR(120)          DEFAULT NULL,
            convenio        VARCHAR(160)          DEFAULT NULL,
            puesto          VARCHAR(160)          DEFAULT NULL,
            salario_base    DECIMAL(12,2) NOT NULL DEFAULT 0,
            jornada         VARCHAR(60)           DEFAULT NULL,
            -- Estado
            estado          VARCHAR(12)  NOT NULL DEFAULT 'activo',  -- activo|baja|suspendido|excedencia
            fecha_alta      DATE                  DEFAULT NULL,
            fecha_baja      DATE                  DEFAULT NULL,
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_emp_nif (id_empresa, nif),
            INDEX idx_emp_estado (id_empresa, estado),
            INDEX idx_emp_usuario (id_usuario),
            INDEX idx_emp_centro (id_centro)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_contratos (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_empleado     BIGINT       NOT NULL,
            tipo_registro   VARCHAR(14)  NOT NULL DEFAULT 'contrato',  -- contrato|renovacion|modificacion|anexo
            modalidad       VARCHAR(40)           DEFAULT NULL,
            fecha_inicio    DATE                  DEFAULT NULL,
            fecha_fin       DATE                  DEFAULT NULL,
            salario         DECIMAL(12,2) NOT NULL DEFAULT 0,
            jornada         VARCHAR(60)           DEFAULT NULL,
            id_centro       CHAR(36)              DEFAULT NULL,
            ref_documento   VARCHAR(255)          DEFAULT NULL,
            datos_snapshot  JSON                  DEFAULT NULL,
            estado          VARCHAR(12)  NOT NULL DEFAULT 'vigente',  -- vigente|finalizado|anulado
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_ctr_empleado (id_empleado, fecha_inicio),
            INDEX idx_ctr_empresa (id_empresa, modalidad),
            CONSTRAINT fk_ctr_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_nominas (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_empleado     BIGINT       NOT NULL,
            anio            SMALLINT     NOT NULL,
            mes             TINYINT      NOT NULL,
            fecha           DATE                  DEFAULT NULL,
            bruto           DECIMAL(12,2) NOT NULL DEFAULT 0,
            base            DECIMAL(12,2) NOT NULL DEFAULT 0,
            irpf_pct        DECIMAL(5,2)  NOT NULL DEFAULT 0,
            irpf_importe    DECIMAL(12,2) NOT NULL DEFAULT 0,
            ss_pct          DECIMAL(5,2)  NOT NULL DEFAULT 0,
            ss_importe      DECIMAL(12,2) NOT NULL DEFAULT 0,
            neto            DECIMAL(12,2) NOT NULL DEFAULT 0,
            conceptos       JSON                  DEFAULT NULL,
            ref_documento   VARCHAR(255)          DEFAULT NULL,
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_nom_periodo (id_empresa, id_empleado, anio, mes),
            INDEX idx_nom_empleado (id_empleado, anio, mes),
            CONSTRAINT fk_nom_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_vacaciones (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_empleado     BIGINT       NOT NULL,
            anio            SMALLINT     NOT NULL,
            tipo            VARCHAR(12)  NOT NULL DEFAULT 'solicitud',  -- saldo|solicitud|aprobacion|denegacion
            fecha_inicio    DATE                  DEFAULT NULL,
            fecha_fin       DATE                  DEFAULT NULL,
            dias            DECIMAL(5,1) NOT NULL DEFAULT 0,
            estado          VARCHAR(12)  NOT NULL DEFAULT 'pendiente',  -- pendiente|aprobada|denegada|consumida
            aprobado_por    VARCHAR(120)          DEFAULT NULL,
            ref_documento   VARCHAR(255)          DEFAULT NULL,
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_vac_empleado (id_empleado, anio),
            CONSTRAINT fk_vac_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_ausencias (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_empleado     BIGINT       NOT NULL,
            tipo            VARCHAR(14)  NOT NULL DEFAULT 'permiso',  -- baja_medica|permiso|justificada|injustificada
            fecha_inicio    DATE                  DEFAULT NULL,
            fecha_fin       DATE                  DEFAULT NULL,
            dias            DECIMAL(5,1) NOT NULL DEFAULT 0,
            motivo          VARCHAR(255)          DEFAULT NULL,
            justificada     TINYINT(1)   NOT NULL DEFAULT 0,
            ref_documento   VARCHAR(255)          DEFAULT NULL,
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_aus_empleado (id_empleado, fecha_inicio),
            CONSTRAINT fk_aus_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_documentos (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_empleado     BIGINT       NOT NULL,
            tipo_doc        VARCHAR(20)  NOT NULL,  -- contrato|nomina|certificado|alta|baja|finiquito|carta_despido|cert_laboral|vacaciones
            fecha           DATE                  DEFAULT NULL,
            ref_documento   VARCHAR(255)          DEFAULT NULL,
            datos_snapshot  JSON                  DEFAULT NULL,
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_doc_empleado (id_empleado, tipo_doc),
            INDEX idx_doc_empresa (id_empresa, fecha),
            CONSTRAINT fk_doc_empleado FOREIGN KEY (id_empleado)
                REFERENCES rrhh_empleados(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    for t in ("rrhh_documentos", "rrhh_ausencias", "rrhh_vacaciones",
              "rrhh_nominas", "rrhh_contratos", "rrhh_empleados"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
