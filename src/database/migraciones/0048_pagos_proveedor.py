"""
Migración 0048 — Pagos a proveedores (rama Tesorería, FASE 4). ADITIVA, idempotente.

`pagos_proveedor` replica el patrón de `ventas_cobros` para el lado AP: pagos parciales,
completos y múltiples contra una factura de compra, con trazabilidad y cuenta bancaria.
"""

VERSION = "0048"
DESCRIPCION = "Pagos a proveedores (parciales/múltiples) patrón ventas_cobros"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pagos_proveedor (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            id_factura_compra INT       DEFAULT NULL,
            id_proveedor  INT          DEFAULT NULL,
            metodo        VARCHAR(16)  NOT NULL DEFAULT 'transferencia',
            importe       DECIMAL(14,2) NOT NULL DEFAULT 0,
            referencia    VARCHAR(80)  DEFAULT NULL,
            estado        VARCHAR(12)  NOT NULL DEFAULT 'pagado',
            id_cuenta     INT          DEFAULT NULL,
            fecha         DATE         DEFAULT NULL,
            usuario       VARCHAR(80)  DEFAULT NULL,
            creado_en     DATETIME     DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pp_emp (id_empresa, id_factura_compra),
            INDEX idx_pp_prov (id_empresa, id_proveedor)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS pagos_proveedor")
