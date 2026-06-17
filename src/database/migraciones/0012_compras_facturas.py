"""
Migración 0012 — Facturas de proveedor (E2.5). ADITIVA y reversible.

compras_facturas (+ líneas), con vínculo opcional a pedido y recepción. Es registro
DOCUMENTAL y de trazabilidad (NO contabilidad). Multiempresa.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0012"
DESCRIPCION = "Facturas de proveedor (compras_facturas, compras_facturas_lineas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_facturas (
            id_factura      BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_proveedor    BIGINT                DEFAULT NULL,
            id_pedido       BIGINT                DEFAULT NULL,
            id_recepcion    BIGINT                DEFAULT NULL,
            numero_factura  VARCHAR(60)           DEFAULT NULL,
            fecha_factura   DATE                  DEFAULT NULL,
            base            DECIMAL(12,2) NOT NULL DEFAULT 0,
            iva             DECIMAL(12,2) NOT NULL DEFAULT 0,
            total           DECIMAL(12,2) NOT NULL DEFAULT 0,
            estado          VARCHAR(16)  NOT NULL DEFAULT 'registrada',
            observaciones   TEXT                  DEFAULT NULL,
            fecha_registro  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cf_emp (id_empresa),
            INDEX idx_cf_prov (id_proveedor),
            INDEX idx_cf_pedido (id_pedido)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compras_facturas_lineas (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_factura      BIGINT       NOT NULL,
            codigo_articulo VARCHAR(50)           DEFAULT NULL,
            descripcion     VARCHAR(255)          DEFAULT NULL,
            cantidad        INT          NOT NULL DEFAULT 0,
            precio_unitario DECIMAL(10,2) NOT NULL DEFAULT 0,
            subtotal        DECIMAL(12,2) NOT NULL DEFAULT 0,
            INDEX idx_cfl_factura (id_factura),
            CONSTRAINT fk_cfl_factura FOREIGN KEY (id_factura)
                REFERENCES compras_facturas(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_facturas_lineas")
    cur.execute("DROP TABLE IF EXISTS compras_facturas")
