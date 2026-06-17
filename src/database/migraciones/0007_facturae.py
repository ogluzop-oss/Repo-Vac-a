"""
Migración 0007 — Facturae (C3.4.1). ADITIVA y reversible.

- `facturae_destinatarios`: datos fiscales estructurados del receptor + códigos DIR3
  (necesarios para Facturae B2G/FACe). La tabla `clientes` no los tiene; esta es
  aditiva y no la modifica.
- `facturae_envios`: seguimiento/estado de envíos a FACe (también actúa como cola
  propia con backoff), SIN tocar el worker congelado de C3.2.

Multiempresa por id_empresa. No contiene secretos. Idempotente.
"""

VERSION = "0007"
DESCRIPCION = "Facturae: destinatarios/DIR3 + seguimiento de envíos FACe"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS facturae_destinatarios (
            id            BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)    NOT NULL,
            cliente_id    INT                  DEFAULT NULL,
            nif           VARCHAR(20) NOT NULL,
            razon_social  VARCHAR(255)         DEFAULT NULL,
            tipo_persona  VARCHAR(1)  NOT NULL DEFAULT 'J',   -- F=física, J=jurídica
            residencia    VARCHAR(1)  NOT NULL DEFAULT 'R',   -- R=residente, U=UE, E=extranjero
            direccion     VARCHAR(255)         DEFAULT NULL,
            cp            VARCHAR(10)          DEFAULT NULL,
            municipio     VARCHAR(120)         DEFAULT NULL,
            provincia     VARCHAR(120)         DEFAULT NULL,
            cod_pais      VARCHAR(3)  NOT NULL DEFAULT 'ESP',
            es_aapp       TINYINT(1)  NOT NULL DEFAULT 0,
            dir3_oficina_contable    VARCHAR(20) DEFAULT NULL,
            dir3_organo_gestor       VARCHAR(20) DEFAULT NULL,
            dir3_unidad_tramitadora  VARCHAR(20) DEFAULT NULL,
            dir3_organo_proponente   VARCHAR(20) DEFAULT NULL,
            fecha         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_fdest (id_empresa, nif),
            INDEX idx_fdest_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS facturae_envios (
            id              BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)    NOT NULL,
            venta_id        INT                  DEFAULT NULL,
            numero_factura  VARCHAR(60)          DEFAULT NULL,
            version         VARCHAR(8)  NOT NULL DEFAULT '3.2.2',
            canal           VARCHAR(12) NOT NULL DEFAULT 'face',  -- face | faceb2b
            estado          VARCHAR(15) NOT NULL DEFAULT 'pendiente',
            numero_registro VARCHAR(80)          DEFAULT NULL,    -- nº registro FACe
            csv             VARCHAR(80)          DEFAULT NULL,
            intentos        INT         NOT NULL DEFAULT 0,
            ultimo_error    VARCHAR(500)         DEFAULT NULL,
            proximo_intento DATETIME             DEFAULT NULL,
            fecha           DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fenv_emp (id_empresa),
            INDEX idx_fenv_estado (estado),
            INDEX idx_fenv_venta (venta_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS facturae_envios")
    cur.execute("DROP TABLE IF EXISTS facturae_destinatarios")
