"""
Migracion 0040 - Presupuestos y pedidos cliente (VTA.6). ADITIVA, reversible, idempotente.
"""
from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0040"
DESCRIPCION = "Presupuestos y pedidos cliente (VTA.6)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    for doc in ("presupuestos", "pedidos_cliente"):
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS ventas_{doc} (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
                id_cliente BIGINT DEFAULT NULL,
                id_tienda INT DEFAULT NULL,
                numero VARCHAR(20) DEFAULT NULL,
                estado VARCHAR(14) NOT NULL DEFAULT 'borrador',
                total DECIMAL(12,2) NOT NULL DEFAULT 0,
                id_venta BIGINT DEFAULT NULL,
                id_origen BIGINT DEFAULT NULL,
                observaciones VARCHAR(255) DEFAULT NULL,
                usuario VARCHAR(120) DEFAULT NULL,
                fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_{doc}_emp (id_empresa, estado)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS ventas_{doc}_lineas (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                id_doc BIGINT NOT NULL,
                id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
                codigo_articulo VARCHAR(50) NOT NULL,
                descripcion VARCHAR(255) DEFAULT NULL,
                cantidad INT NOT NULL DEFAULT 0,
                precio_unitario DECIMAL(10,2) NOT NULL DEFAULT 0,
                subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
                reservado TINYINT(1) NOT NULL DEFAULT 0,
                INDEX idx_{doc}l_doc (id_doc)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS ventas_presupuestos_lineas")
    cur.execute("DROP TABLE IF EXISTS ventas_presupuestos")
    cur.execute("DROP TABLE IF EXISTS ventas_pedidos_cliente_lineas")
    cur.execute("DROP TABLE IF EXISTS ventas_pedidos_cliente")
