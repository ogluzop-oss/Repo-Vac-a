"""
Migración 0033 — Costes reales/ampliados de compras (CMP.6). ADITIVA, reversible.
Costes indirectos (transporte/aduanas/importación/seguros/manipulación/otros) por recepción
para prorratear sobre el coste de los artículos recibidos.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0033"
DESCRIPCION = "Costes ampliados: compras_costes_extra"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_costes_extra (
            id           BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa   CHAR(36) NOT NULL DEFAULT '{emp}',
            id_recepcion BIGINT               DEFAULT NULL,
            id_pedido    BIGINT               DEFAULT NULL,
            tipo         VARCHAR(20) NOT NULL,  -- transporte|aduanas|importacion|seguro|manipulacion|otros
            importe      DECIMAL(12,2) NOT NULL DEFAULT 0,
            prorrateado  TINYINT(1)  NOT NULL DEFAULT 0,
            descripcion  VARCHAR(255)         DEFAULT NULL,
            fecha        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cex_empresa (id_empresa),
            INDEX idx_cex_recepcion (id_recepcion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_costes_extra")
