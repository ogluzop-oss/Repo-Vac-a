"""
Migracion 0079 — Ciclo financiero de la factura (FASE 3.6). ADITIVA, reversible, idempotente.

- factura_cobros: cobros de una factura (mixto/parcial: varias filas = varios medios de pago).
- facturas_cliente.id_vencimiento: enlace al vencimiento AR (cuentas a cobrar) ya existente.

NO duplica tesorería: los vencimientos siguen en `vencimientos` (motor único). Aditivo: las
facturas existentes quedan sin cobros detallados ni vencimiento (comportamiento actual).
"""

VERSION = "0079"
DESCRIPCION = "factura_cobros + facturas_cliente.id_vencimiento (ciclo financiero / cobro mixto / AR)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factura_cobros (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_factura BIGINT NOT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            importe DECIMAL(12,2) NOT NULL DEFAULT 0,
            forma_pago VARCHAR(20) DEFAULT NULL,
            referencia VARCHAR(80) DEFAULT NULL,
            id_usuario BIGINT DEFAULT NULL,
            INDEX idx_fcob_factura (id_factura),
            CONSTRAINT fk_fcob_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("ALTER TABLE facturas_cliente ADD COLUMN IF NOT EXISTS id_vencimiento BIGINT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS id_vencimiento")
    cur.execute("DROP TABLE IF EXISTS factura_cobros")
