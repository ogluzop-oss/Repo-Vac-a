"""
Migración 0010 — Recepción de compra contra pedido (E2.3). ADITIVA y reversible.

compras_recepciones (cabecera) + compras_recepciones_lineas. Cada recepción puede
ser parcial; suma a `compras_pedidos_lineas.cantidad_recibida` y genera movimientos
de stock (tabla `movimientos_stock` existente, reutilizada). No toca el flujo de
recepción logística por palé (es independiente y complementario).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0010"
DESCRIPCION = "Recepción de compra (compras_recepciones, compras_recepciones_lineas)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compras_recepciones (
            id_recepcion    BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_pedido       BIGINT       NOT NULL,
            usuario         VARCHAR(100)          DEFAULT NULL,
            observaciones   TEXT                  DEFAULT NULL,
            total_unidades  INT          NOT NULL DEFAULT 0,
            fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cr_emp (id_empresa),
            INDEX idx_cr_pedido (id_pedido),
            CONSTRAINT fk_cr_pedido FOREIGN KEY (id_pedido)
                REFERENCES compras_pedidos(id_pedido) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compras_recepciones_lineas (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_recepcion    BIGINT       NOT NULL,
            id_linea_pedido BIGINT                DEFAULT NULL,
            codigo_articulo VARCHAR(50)           DEFAULT NULL,
            cantidad        INT          NOT NULL DEFAULT 0,
            INDEX idx_crl_rec (id_recepcion),
            CONSTRAINT fk_crl_rec FOREIGN KEY (id_recepcion)
                REFERENCES compras_recepciones(id_recepcion) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_recepciones_lineas")
    cur.execute("DROP TABLE IF EXISTS compras_recepciones")
