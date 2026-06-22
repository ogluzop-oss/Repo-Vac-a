"""
Migración 0050 — SEPA (rama Tesorería, FASE 9). ADITIVA, idempotente.

  • mandatos_sepa: mandatos de adeudo (CORE/B2B), IBAN del deudor cifrado en reposo.
  • remesas_sepa: cabecera de remesa (TRANSFER pain.001 / ADEUDO pain.008) con estados.
  • remesa_lineas: operaciones de la remesa (beneficiario/deudor, importe, end-to-end).
"""

VERSION = "0050"
DESCRIPCION = "SEPA: mandatos + remesas (pain.001/pain.008) + líneas"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mandatos_sepa (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            referencia_mandato VARCHAR(35) NOT NULL,
            tipo          VARCHAR(4)   NOT NULL DEFAULT 'CORE',
            nombre_deudor VARCHAR(160) DEFAULT NULL,
            iban_deudor   VARCHAR(255) DEFAULT NULL,
            iban_mascara  VARCHAR(40)  DEFAULT NULL,
            bic           VARCHAR(16)  DEFAULT NULL,
            fecha_firma   DATE         DEFAULT NULL,
            estado        VARCHAR(12)  NOT NULL DEFAULT 'activo',
            creado_en     DATETIME     DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_mand_emp (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("ALTER TABLE mandatos_sepa ADD UNIQUE INDEX IF NOT EXISTS "
                "uq_mandato (id_empresa, referencia_mandato)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS remesas_sepa (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            tipo          VARCHAR(10)  NOT NULL DEFAULT 'TRANSFER',
            estado        VARCHAR(12)  NOT NULL DEFAULT 'borrador',
            id_cuenta     INT          DEFAULT NULL,
            mensaje_id    VARCHAR(35)  DEFAULT NULL,
            num_operaciones INT        NOT NULL DEFAULT 0,
            importe_total DECIMAL(14,2) NOT NULL DEFAULT 0,
            fichero_xml   LONGTEXT     DEFAULT NULL,
            fecha_creacion DATETIME    DEFAULT CURRENT_TIMESTAMP,
            fecha_ejecucion DATE       DEFAULT NULL,
            INDEX idx_rem_emp (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS remesa_lineas (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            id_remesa     INT          NOT NULL,
            nombre_tercero VARCHAR(160) DEFAULT NULL,
            iban          VARCHAR(255) DEFAULT NULL,
            bic           VARCHAR(16)  DEFAULT NULL,
            importe       DECIMAL(14,2) NOT NULL DEFAULT 0,
            concepto      VARCHAR(140) DEFAULT NULL,
            end_to_end_id VARCHAR(35)  DEFAULT NULL,
            id_mandato    INT          DEFAULT NULL,
            id_vencimiento INT         DEFAULT NULL,
            INDEX idx_rl_remesa (id_remesa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS remesa_lineas")
    cur.execute("DROP TABLE IF EXISTS remesas_sepa")
    cur.execute("DROP TABLE IF EXISTS mandatos_sepa")
