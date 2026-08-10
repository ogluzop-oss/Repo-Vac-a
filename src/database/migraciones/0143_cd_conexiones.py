"""
Migración 0143 — PCD · Etapa B · Fase B1: Conexiones de canal + credenciales seguras.

Registro por tenant (multiempresa/multitienda) de las conexiones a servicios externos (marketplaces,
pasarelas, transportistas, canales propios). Las credenciales se guardan SIEMPRE CIFRADAS (secret
manager Enterprise) o por referencia a secreto externo; NUNCA en claro ni en código.

ADITIVA, idempotente, reversible (tabla nueva → revert la elimina). No elimina ni altera datos.
"""

VERSION = "0143"
DESCRIPCION = "PCD Etapa B/F1: cd_conexiones (conexiones de canal + credenciales cifradas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_conexiones", """
        id                     BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa             CHAR(36)              DEFAULT NULL,
        id_tienda              INT                   DEFAULT NULL,   -- NULL = toda la empresa
        canal                  VARCHAR(40)  NOT NULL,                -- clave del conector (woocommerce/stripe/mrw/…)
        nombre                 VARCHAR(120) NOT NULL DEFAULT 'default',
        tipo_auth              VARCHAR(20)  NOT NULL DEFAULT 'apikey', -- apikey|oauth2|basic|hmac|none
        endpoint_base          VARCHAR(255)          DEFAULT NULL,
        config                 MEDIUMTEXT,                            -- config NO sensible (JSON)
        credenciales_cifradas  MEDIUMTEXT,                            -- secreto CIFRADO (nunca en claro)
        secret_ref             VARCHAR(120)          DEFAULT NULL,    -- nombre de secreto externo (alternativa)
        estado                 VARCHAR(16)  NOT NULL DEFAULT 'ACTIVA', -- ACTIVA|INACTIVA|ERROR
        ultimo_test            DATETIME              DEFAULT NULL,
        ultimo_resultado       VARCHAR(255)          DEFAULT NULL,
        actor                  VARCHAR(120)          DEFAULT NULL,
        ts_creado              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_actualizado         DATETIME              DEFAULT NULL,
        UNIQUE KEY uq_conexion (id_empresa, canal, nombre),
        INDEX idx_conx_canal (id_empresa, canal),
        INDEX idx_conx_estado (id_empresa, estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
