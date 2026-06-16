"""
Migración 0002 — Modelo fiscal base (C3.1).

Crea las tablas del núcleo fiscal (sin lógica legal aún):
- `fiscal_config`    : configuración fiscal POR EMPRESA (territorio, modo, proveedor…).
- `fiscal_registros` : registros de facturación con ENCADENADO HASH (por empresa+serie).
- `fiscal_cola`      : cola de envío/reenvío (idempotente, con reintentos).

Aditiva e idempotente (CREATE IF NOT EXISTS). Reversible. No contiene secretos.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0002"
DESCRIPCION = "Modelo fiscal base (config, registros encadenados, cola de envío)"
REVERSIBLE = True
REQUIERE_BACKUP = True


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS fiscal_config (
            id_empresa  CHAR(36)     NOT NULL PRIMARY KEY,
            territorio  VARCHAR(20)  NOT NULL DEFAULT 'comun',
            modo        VARCHAR(20)  NOT NULL DEFAULT 'verifactu',
            proveedor   VARCHAR(30)  NOT NULL DEFAULT 'simulado',
            integrador  VARCHAR(60)           DEFAULT NULL,
            serie       VARCHAR(20)  NOT NULL DEFAULT 'A',
            activo      TINYINT(1)   NOT NULL DEFAULT 0,
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS fiscal_registros (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_tienda     INT                   DEFAULT NULL,
            serie         VARCHAR(20)  NOT NULL DEFAULT 'A',
            numero        BIGINT       NOT NULL,
            tipo          VARCHAR(20)  NOT NULL,
            referencia    VARCHAR(64)           DEFAULT NULL,
            total         DECIMAL(12,2) NOT NULL DEFAULT 0,
            hash          CHAR(64)     NOT NULL,
            hash_anterior CHAR(64)              DEFAULT NULL,
            qr            TEXT                  DEFAULT NULL,
            payload       MEDIUMTEXT            DEFAULT NULL,
            proveedor     VARCHAR(30)  NOT NULL DEFAULT 'simulado',
            estado        VARCHAR(20)  NOT NULL DEFAULT 'generado',
            fecha         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_fiscal_serie (id_empresa, serie, numero),
            INDEX idx_fr_emp (id_empresa), INDEX idx_fr_ref (referencia)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS fiscal_cola (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_registro   BIGINT       NOT NULL,
            accion        VARCHAR(20)  NOT NULL DEFAULT 'enviar',
            estado        VARCHAR(20)  NOT NULL DEFAULT 'pendiente',
            intentos      INT          NOT NULL DEFAULT 0,
            ultimo_error  VARCHAR(500)          DEFAULT NULL,
            proximo_intento DATETIME            DEFAULT NULL,
            fecha         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fc_estado (estado), INDEX idx_fc_registro (id_registro)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
