"""
Migracion 0071 — Facturacion Profesional Avanzada (Enterprise), FASE 2 · paso 1. ADITIVA, reversible, idempotente.

Crea SOLO tablas/columnas NUEVAS; no toca ninguna tabla existente ni su logica:

- factura_fiscal     : puente factura comercial <-> fiscal_registros (D1, enlace fiscal).
- factura_impuestos  : desglose de IVA por linea/tipo de una factura (D-multi-IVA, F-04).
- factura_eventos    : traza de auditoria (generada/vista/descargada/anulada...) (F-07).
- factura_qr         : QR fiscal asociado a la factura comercial (reuso del QR del registro).
- facturas_cliente.snapshot(+snapshot_fecha) : congelado documental inmutable al emitir (F-06).

Multiempresa (id_empresa CHAR(36)). FK con ON DELETE CASCADE hacia facturas_cliente para
mantener consistencia. No contiene secretos. Numeracion/serie y anulacion se abordan en
pasos posteriores del roadmap (este paso solo provisiona el modelo de datos).
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0071"
DESCRIPCION = "Facturacion Enterprise (paso 1): factura_fiscal/impuestos/eventos/qr + snapshot documental"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID

    # 1) Puente factura comercial <-> registro fiscal (Verifactu). Una factura -> un registro.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS factura_fiscal (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_factura BIGINT NOT NULL,
            id_registro_fiscal BIGINT DEFAULT NULL,
            serie_fiscal VARCHAR(20) DEFAULT NULL,
            numero_fiscal BIGINT DEFAULT NULL,
            hash CHAR(64) DEFAULT NULL,
            hash_anterior CHAR(64) DEFAULT NULL,
            estado_fiscal VARCHAR(20) NOT NULL DEFAULT 'pendiente',
            estado_aeat VARCHAR(20) DEFAULT NULL,
            csv_aeat VARCHAR(64) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_ff_factura (id_empresa, id_factura),
            INDEX idx_ff_reg (id_registro_fiscal),
            CONSTRAINT fk_ff_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 2) Desglose de impuestos por linea/tipo. id_linea NULL = fila resumen por tipo.
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS factura_impuestos (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_factura BIGINT NOT NULL,
            id_linea BIGINT DEFAULT NULL,
            tipo_iva DECIMAL(5,2) NOT NULL DEFAULT 0,
            base DECIMAL(12,2) NOT NULL DEFAULT 0,
            cuota DECIMAL(12,2) NOT NULL DEFAULT 0,
            total DECIMAL(12,2) NOT NULL DEFAULT 0,
            tipo_recargo DECIMAL(5,2) DEFAULT NULL,
            cuota_recargo DECIMAL(12,2) DEFAULT NULL,
            INDEX idx_fi_factura (id_factura),
            CONSTRAINT fk_fi_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 3) Traza de auditoria de la factura (quien/que/cuando).
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS factura_eventos (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_factura BIGINT NOT NULL,
            evento VARCHAR(30) NOT NULL,
            id_usuario BIGINT DEFAULT NULL,
            usuario VARCHAR(80) DEFAULT NULL,
            detalle VARCHAR(500) DEFAULT NULL,
            ip VARCHAR(45) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fe_factura (id_factura),
            INDEX idx_fe_evento (id_empresa, evento),
            CONSTRAINT fk_fe_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 4) QR fiscal de la factura comercial (contenido + opcional imagen renderizada).
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS factura_qr (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) NOT NULL DEFAULT '{emp}',
            id_factura BIGINT NOT NULL,
            contenido TEXT DEFAULT NULL,
            formato VARCHAR(20) NOT NULL DEFAULT 'verifactu',
            imagen_path VARCHAR(255) DEFAULT NULL,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_fq_factura (id_empresa, id_factura),
            CONSTRAINT fk_fq_factura FOREIGN KEY (id_factura)
                REFERENCES facturas_cliente(id_factura) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 5) Snapshot documental inmutable en la propia factura (JSON congelado al emitir).
    cur.execute("ALTER TABLE facturas_cliente ADD COLUMN IF NOT EXISTS snapshot LONGTEXT DEFAULT NULL")
    cur.execute("ALTER TABLE facturas_cliente ADD COLUMN IF NOT EXISTS snapshot_fecha DATETIME DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS snapshot_fecha")
    cur.execute("ALTER TABLE facturas_cliente DROP COLUMN IF EXISTS snapshot")
    for t in ("factura_qr", "factura_eventos", "factura_impuestos", "factura_fiscal"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
