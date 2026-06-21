"""
Migración 0021 — Inventario físico / recuento auditado (INV.2). ADITIVA y reversible.

Cabecera `inventarios` + líneas `inventario_lineas`. No altera articulos/movimientos_stock
(el ajuste al cerrar usa la infraestructura de INV.1). Multiempresa/multitienda.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0021"
DESCRIPCION = "Inventario físico: inventarios + inventario_lineas"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS inventarios (
            id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa       CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_tienda        INT                   DEFAULT NULL,
            nombre           VARCHAR(120) NOT NULL DEFAULT '',
            estado           VARCHAR(12)  NOT NULL DEFAULT 'BORRADOR',  -- BORRADOR|ABIERTO|CERRADO|ANULADO
            fecha_apertura   DATETIME              DEFAULT NULL,
            fecha_cierre     DATETIME              DEFAULT NULL,
            usuario_creacion VARCHAR(120)          DEFAULT NULL,
            usuario_cierre   VARCHAR(120)          DEFAULT NULL,
            observaciones    TEXT                  DEFAULT NULL,
            created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_inv_empresa (id_empresa, estado),
            INDEX idx_inv_tienda (id_tienda)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS inventario_lineas (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_inventario   BIGINT       NOT NULL,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            codigo_articulo VARCHAR(50)  NOT NULL,
            stock_esperado  INT          NOT NULL DEFAULT 0,
            stock_contado   INT                   DEFAULT NULL,
            diferencia      INT          NOT NULL DEFAULT 0,
            observaciones   VARCHAR(255)          DEFAULT NULL,
            actualizado_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_inv_linea (id_inventario, codigo_articulo),
            INDEX idx_invl_empresa (id_empresa),
            INDEX idx_invl_articulo (codigo_articulo),
            CONSTRAINT fk_invl_inv FOREIGN KEY (id_inventario)
                REFERENCES inventarios(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS inventario_lineas")
    cur.execute("DROP TABLE IF EXISTS inventarios")
