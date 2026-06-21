"""
Migración 0022 — Lotes, caducidades y FEFO (INV.3). ADITIVA y reversible.

Sub-ledger paralelo al stock agregado (articulos/stock_tienda): `lotes` (existencias por
lote + caducidad) y `lotes_movimientos` (trazabilidad por lote). No altera articulos ni
movimientos_stock; el stock agregado sigue siendo la fuente de verdad y la integración es
best-effort. Multiempresa/multitienda (id_tienda 0 = sin tienda/global).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0022"
DESCRIPCION = "Lotes y caducidades: lotes + lotes_movimientos"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS lotes (
            id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa       CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_tienda        INT          NOT NULL DEFAULT 0,
            codigo_articulo  VARCHAR(50)  NOT NULL,
            lote             VARCHAR(60)  NOT NULL,
            fecha_caducidad  DATE                  DEFAULT NULL,
            cantidad         INT          NOT NULL DEFAULT 0,
            cantidad_inicial INT          NOT NULL DEFAULT 0,
            origen           VARCHAR(30)           DEFAULT NULL,
            id_documento     VARCHAR(50)           DEFAULT NULL,
            estado           VARCHAR(10)  NOT NULL DEFAULT 'activo',  -- activo|agotado
            fecha_entrada    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_lote (id_empresa, id_tienda, codigo_articulo, lote),
            INDEX idx_lote_fefo (id_empresa, codigo_articulo, estado, fecha_caducidad),
            INDEX idx_lote_caduc (id_empresa, fecha_caducidad)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS lotes_movimientos (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_lote         BIGINT       NOT NULL,
            codigo_articulo VARCHAR(50)  NOT NULL,
            tipo            VARCHAR(20)  NOT NULL,  -- ENTRADA|SALIDA_VENTA|MERMA|TRASPASO|AJUSTE|DEVOLUCION
            cantidad        INT          NOT NULL DEFAULT 0,
            id_documento    VARCHAR(50)           DEFAULT NULL,
            usuario         VARCHAR(100)          DEFAULT NULL,
            observaciones   VARCHAR(255)          DEFAULT NULL,
            fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_lm_lote (id_lote),
            INDEX idx_lm_articulo (id_empresa, codigo_articulo),
            CONSTRAINT fk_lm_lote FOREIGN KEY (id_lote)
                REFERENCES lotes(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS lotes_movimientos")
    cur.execute("DROP TABLE IF EXISTS lotes")
