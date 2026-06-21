"""
Migracion 0042 - Facturacion comercial (VTA.8): facturas_cliente(+lineas). ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0042"
DESCRIPCION = "Facturacion comercial (VTA.8): facturas_cliente(+lineas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS facturas_cliente (
            id_factura BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_cliente BIGINT DEFAULT NULL,
            id_venta BIGINT DEFAULT NULL,
            id_tienda INT DEFAULT NULL,
            numero VARCHAR(20) DEFAULT NULL,
            serie VARCHAR(10) DEFAULT NULL,
            estado VARCHAR(10) NOT NULL DEFAULT 'borrador',
            base DECIMAL(12,2) NOT NULL DEFAULT 0,
            iva DECIMAL(12,2) NOT NULL DEFAULT 0,
            total DECIMAL(12,2) NOT NULL DEFAULT 0,
            cobrado DECIMAL(12,2) NOT NULL DEFAULT 0,
            fecha_emision DATE DEFAULT NULL,
            fecha_vencimiento DATE DEFAULT NULL,
            observaciones VARCHAR(255) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fc_emp (id_empresa, estado),
            INDEX idx_fc_cliente (id_cliente)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS facturas_cliente_lineas (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_factura BIGINT NOT NULL,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            codigo_articulo VARCHAR(50) DEFAULT NULL,
            descripcion VARCHAR(255) DEFAULT NULL,
            cantidad INT NOT NULL DEFAULT 0,
            precio_unitario DECIMAL(10,2) NOT NULL DEFAULT 0,
            coste_unitario DECIMAL(10,2) NOT NULL DEFAULT 0,
            subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
            INDEX idx_fcl_fac (id_factura),
            CONSTRAINT fk_fcl_fac FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS facturas_cliente_lineas")
    cur.execute("DROP TABLE IF EXISTS facturas_cliente")
