"""
Migracion 0084 — EDI/PEPPOL + Portal del cliente (FASE 4.9/4.10/4.4). ADITIVA, reversible, idempotente.

- factura_edi: intercambio documental B2B (EDIFACT/UBL/XML B2B/PEPPOL). Estructura preparada
  (no se activa producción ni se certifica PEPPOL: solo arquitectura).
- portal_cliente_log: trazabilidad del portal del cliente (login/visualización/descarga).
"""

VERSION = "0084"
DESCRIPCION = "factura_edi + portal_cliente_log (FASE 4.9/4.10/4.4)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS factura_edi (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_factura BIGINT NOT NULL,
            formato VARCHAR(15) NOT NULL DEFAULT 'ubl',
            canal VARCHAR(15) DEFAULT NULL,
            estado VARCHAR(20) NOT NULL DEFAULT 'preparado',
            fecha_envio DATETIME DEFAULT NULL,
            fecha_recepcion DATETIME DEFAULT NULL,
            respuesta VARCHAR(400) DEFAULT NULL,
            ruta VARCHAR(400) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_edi_factura (id_factura),
            CONSTRAINT fk_edi_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portal_cliente_log (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL,
            id_cliente BIGINT DEFAULT NULL,
            evento VARCHAR(30) NOT NULL,
            id_factura BIGINT DEFAULT NULL,
            detalle VARCHAR(255) DEFAULT NULL,
            ip VARCHAR(45) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_portal_cli (id_empresa, id_cliente)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS portal_cliente_log")
    cur.execute("DROP TABLE IF EXISTS factura_edi")
