"""
Migración 0009 — Pedidos de compra (E2.2). ADITIVA y reversible.

compras_pedidos (cabecera) + compras_pedidos_lineas. Multiempresa. Las líneas
referencian `articulos.codigo` por valor (validación blanda, sin FK rígida: se
permiten artículos que aún no existan en el maestro). `cantidad_recibida` se usa en
la recepción contra pedido (E2.3).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0009"
DESCRIPCION = "Pedidos de compra (compras_pedidos, compras_pedidos_lineas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_pedidos (
            id_pedido       BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_proveedor    BIGINT                DEFAULT NULL,
            numero          VARCHAR(30)           DEFAULT NULL,
            estado          VARCHAR(12)  NOT NULL DEFAULT 'BORRADOR',
            total           DECIMAL(12,2) NOT NULL DEFAULT 0,
            observaciones   TEXT                  DEFAULT NULL,
            usuario         VARCHAR(100)          DEFAULT NULL,
            fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_envio     DATETIME              DEFAULT NULL,
            fecha_recepcion DATETIME              DEFAULT NULL,
            INDEX idx_cp_emp (id_empresa),
            INDEX idx_cp_estado (estado),
            INDEX idx_cp_prov (id_proveedor)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compras_pedidos_lineas (
            id                BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_pedido         BIGINT       NOT NULL,
            codigo_articulo   VARCHAR(50)           DEFAULT NULL,
            descripcion       VARCHAR(255)          DEFAULT NULL,
            cantidad          INT          NOT NULL DEFAULT 0,
            cantidad_recibida INT          NOT NULL DEFAULT 0,
            precio_unitario   DECIMAL(10,2) NOT NULL DEFAULT 0,
            subtotal          DECIMAL(12,2) NOT NULL DEFAULT 0,
            INDEX idx_cpl_pedido (id_pedido),
            INDEX idx_cpl_cod (codigo_articulo),
            CONSTRAINT fk_cpl_pedido FOREIGN KEY (id_pedido)
                REFERENCES compras_pedidos(id_pedido) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_pedidos_lineas")
    cur.execute("DROP TABLE IF EXISTS compras_pedidos")
