"""
Migración 0047 — Vencimientos AR/AP (rama Tesorería, FASE 3). ADITIVA, idempotente.

`vencimientos` unifica cuentas a cobrar (COBRO) y a pagar (PAGO) de cualquier origen
(factura_cliente, compra_factura, nomina, impuesto, manual). `pendiente` decrece con cada
cobro/pago; la idempotencia evita duplicar un vencimiento del mismo documento.
"""

VERSION = "0047"
DESCRIPCION = "Vencimientos unificados (AR/AP) con estados y pendiente"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vencimientos (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            tipo          VARCHAR(8)   NOT NULL,
            fecha_vencimiento DATE     NOT NULL,
            importe       DECIMAL(14,2) NOT NULL DEFAULT 0,
            pendiente     DECIMAL(14,2) NOT NULL DEFAULT 0,
            estado        VARCHAR(10)  NOT NULL DEFAULT 'PENDIENTE',
            origen        VARCHAR(24)  NOT NULL DEFAULT 'manual',
            id_documento  VARCHAR(80)  DEFAULT NULL,
            tercero       VARCHAR(160) DEFAULT NULL,
            concepto      VARCHAR(255) DEFAULT NULL,
            creado_en     DATETIME     DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_venc_estado (id_empresa, estado, fecha_vencimiento),
            INDEX idx_venc_tipo (id_empresa, tipo, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("ALTER TABLE vencimientos ADD UNIQUE INDEX IF NOT EXISTS "
                "uq_venc (id_empresa, origen, tipo, id_documento)")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS vencimientos")
