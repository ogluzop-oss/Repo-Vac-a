"""
Migración 0035 — Clientes profesionales (VTA.1). ADITIVA, reversible, idempotente.

Amplía `clientes` (crédito/riesgo/segmentación) y crea `clientes_contactos` y
`clientes_direcciones`. No elimina ni cambia nada existente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0035"
DESCRIPCION = "Clientes PRO: crédito/segmentación + contactos + direcciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("limite_credito", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
    ("riesgo_actual", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
    ("categoria", "VARCHAR(50) DEFAULT NULL"),
    ("segmento", "VARCHAR(50) DEFAULT NULL"),
    ("observaciones", "TEXT DEFAULT NULL"),
    ("estado_crediticio", "VARCHAR(12) NOT NULL DEFAULT 'normal'"),
]


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE clientes ADD COLUMN IF NOT EXISTS {col} {ddl}")
    cur.execute("ALTER TABLE clientes ADD INDEX IF NOT EXISTS idx_cli_segmento (id_empresa, segmento)")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS clientes_contactos (
            id          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_cliente  INT NOT NULL,
            id_empresa  CHAR(36) NOT NULL DEFAULT '{emp}',
            nombre      VARCHAR(120) DEFAULT NULL,
            cargo       VARCHAR(80)  DEFAULT NULL,
            email       VARCHAR(120) DEFAULT NULL,
            telefono    VARCHAR(40)  DEFAULT NULL,
            fecha       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_clic_cli (id_cliente),
            CONSTRAINT fk_clic_cli FOREIGN KEY (id_cliente)
                REFERENCES clientes(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS clientes_direcciones (
            id          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_cliente  INT NOT NULL,
            id_empresa  CHAR(36) NOT NULL DEFAULT '{emp}',
            tipo        VARCHAR(20) NOT NULL DEFAULT 'envio',
            direccion   VARCHAR(255) DEFAULT NULL,
            cp          VARCHAR(12)  DEFAULT NULL,
            municipio   VARCHAR(120) DEFAULT NULL,
            provincia   VARCHAR(120) DEFAULT NULL,
            pais        VARCHAR(60)  DEFAULT NULL,
            fecha       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_clid_cli (id_cliente),
            CONSTRAINT fk_clid_cli FOREIGN KEY (id_cliente)
                REFERENCES clientes(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS clientes_direcciones")
    cur.execute("DROP TABLE IF EXISTS clientes_contactos")
    cur.execute("ALTER TABLE clientes DROP INDEX IF EXISTS idx_cli_segmento")
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE clientes DROP COLUMN IF EXISTS {col}")
