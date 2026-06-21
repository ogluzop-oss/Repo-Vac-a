"""
Migración 0030 — Recepción avanzada (CMP.3). ADITIVA, reversible, idempotente.

Amplía `compras_recepciones_lineas` con lote/caducidad/fabricación/proveedor_origen y crea
`compras_incidencias`. No altera el flujo de recepción existente (campos nuevos opcionales).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0030"
DESCRIPCION = "Recepción avanzada: líneas con lote/caducidad + compras_incidencias"
REVERSIBLE = True
REQUIERE_BACKUP = False

_LIN = [
    ("lote", "VARCHAR(60) DEFAULT NULL"),
    ("fecha_caducidad", "DATE DEFAULT NULL"),
    ("fecha_fabricacion", "DATE DEFAULT NULL"),
    ("proveedor_origen", "VARCHAR(120) DEFAULT NULL"),
    ("id_almacen", "INT DEFAULT NULL"),
]


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    for col, ddl in _LIN:
        cur.execute(f"ALTER TABLE compras_recepciones_lineas ADD COLUMN IF NOT EXISTS {col} {ddl}")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_incidencias (
            id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_pedido     BIGINT                DEFAULT NULL,
            id_recepcion  BIGINT                DEFAULT NULL,
            id_proveedor  BIGINT                DEFAULT NULL,
            codigo_articulo VARCHAR(50)         DEFAULT NULL,
            tipo          VARCHAR(20)  NOT NULL,  -- danado|faltante|exceso|rechazo|error_prov|otros
            cantidad      INT          NOT NULL DEFAULT 0,
            estado        VARCHAR(12)  NOT NULL DEFAULT 'abierta',  -- abierta|resuelta|anulada
            descripcion   VARCHAR(255)          DEFAULT NULL,
            usuario       VARCHAR(120)          DEFAULT NULL,
            fecha         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_inc_empresa (id_empresa, estado),
            INDEX idx_inc_pedido (id_pedido),
            INDEX idx_inc_proveedor (id_proveedor)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_incidencias")
    for col, _ in _LIN:
        cur.execute(f"ALTER TABLE compras_recepciones_lineas DROP COLUMN IF EXISTS {col}")
