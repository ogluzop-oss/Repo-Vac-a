"""
Migracion 0080 — Distribucion documental de la factura (FASE 3.8). ADITIVA, reversible, idempotente.

- factura_envios: registro de envios (email / FACe / FACeB2B / futuros canales) con estado y reintentos.
- factura_exportaciones: registro de exportaciones (PDF / Facturae / XML / CSV / futuros formatos).

Trazabilidad completa (usuario/fecha/canal/resultado/destino), tenant-aware (id_empresa). Aditivo:
no altera facturas existentes. Reutiliza factura_eventos para los eventos enviada/exportada.
"""

VERSION = "0080"
DESCRIPCION = "factura_envios + factura_exportaciones (distribucion documental)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factura_envios (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_factura BIGINT NOT NULL,
            canal VARCHAR(20) NOT NULL DEFAULT 'email',
            destinatario VARCHAR(160) DEFAULT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
            intentos INT NOT NULL DEFAULT 0,
            ultimo_error VARCHAR(400) DEFAULT NULL,
            id_usuario BIGINT DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fenv_factura (id_factura),
            INDEX idx_fenv_estado (id_empresa, estado),
            CONSTRAINT fk_fenv_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factura_exportaciones (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_factura BIGINT NOT NULL,
            formato VARCHAR(20) NOT NULL DEFAULT 'pdf',
            ruta VARCHAR(400) DEFAULT NULL,
            hash CHAR(64) DEFAULT NULL,
            destino VARCHAR(120) DEFAULT NULL,
            id_usuario BIGINT DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fexp_factura (id_factura),
            CONSTRAINT fk_fexp_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS factura_exportaciones")
    cur.execute("DROP TABLE IF EXISTS factura_envios")
