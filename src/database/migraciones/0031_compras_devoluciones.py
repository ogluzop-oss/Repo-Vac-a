"""
Migración 0031 — Devoluciones a proveedor (CMP.4). ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0031"
DESCRIPCION = "Devoluciones a proveedor: compras_devoluciones(+lineas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_devoluciones (
            id_devolucion BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa   CHAR(36)    NOT NULL DEFAULT '{emp}',
            id_proveedor BIGINT               DEFAULT NULL,
            id_pedido    BIGINT               DEFAULT NULL,
            id_almacen   INT                  DEFAULT NULL,
            motivo       VARCHAR(255)         DEFAULT NULL,
            estado       VARCHAR(12) NOT NULL DEFAULT 'registrada',
            total        DECIMAL(12,2) NOT NULL DEFAULT 0,
            usuario      VARCHAR(120)         DEFAULT NULL,
            fecha        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_dev_empresa (id_empresa, estado),
            INDEX idx_dev_proveedor (id_proveedor)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_devoluciones_lineas (
            id            BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_devolucion BIGINT NOT NULL,
            id_empresa    CHAR(36) NOT NULL DEFAULT '{emp}',
            codigo_articulo VARCHAR(50) NOT NULL,
            lote          VARCHAR(60)          DEFAULT NULL,
            cantidad      INT          NOT NULL DEFAULT 0,
            precio_unitario DECIMAL(10,2) NOT NULL DEFAULT 0,
            subtotal      DECIMAL(12,2) NOT NULL DEFAULT 0,
            motivo        VARCHAR(255)         DEFAULT NULL,
            INDEX idx_devl_dev (id_devolucion),
            CONSTRAINT fk_devl_dev FOREIGN KEY (id_devolucion)
                REFERENCES compras_devoluciones(id_devolucion) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_devoluciones_lineas")
    cur.execute("DROP TABLE IF EXISTS compras_devoluciones")
