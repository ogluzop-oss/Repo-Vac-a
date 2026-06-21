"""
Migración 0019 — Firma/aceptación documental RRHH (F4.11). ADITIVA y reversible.

Amplía `rrhh_documentos` con estado de firma (requiere_firma, estado_firma, fechas,
hash documental, firmante, versión, expiración) y añade `rrhh_doc_auditoria` (registro
append-only de acciones: emisión/aceptación/rechazo/anulación). No reescribe el sistema
documental; solo lo amplía. Multiempresa.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0019"
DESCRIPCION = "Firma/aceptación documental RRHH (rrhh_documentos + rrhh_doc_auditoria)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("requiere_firma", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("estado_firma", "VARCHAR(12) NOT NULL DEFAULT 'pendiente'"),  # pendiente|aceptado|rechazado|expirado|anulado
    ("fecha_aceptacion", "DATETIME DEFAULT NULL"),
    ("fecha_rechazo", "DATETIME DEFAULT NULL"),
    ("hash_documental", "CHAR(64) DEFAULT NULL"),
    ("firmado_por", "VARCHAR(120) DEFAULT NULL"),
    ("version_doc", "INT NOT NULL DEFAULT 1"),
    ("expira", "DATE DEFAULT NULL"),
]


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE rrhh_documentos ADD COLUMN IF NOT EXISTS {col} {ddl}")
    cur.execute("ALTER TABLE rrhh_documentos ADD INDEX IF NOT EXISTS "
                "idx_doc_firma (id_empresa, requiere_firma, estado_firma)")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS rrhh_doc_auditoria (
            id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa     CHAR(36)     NOT NULL DEFAULT '{emp}',
            id_documento   BIGINT       NOT NULL,
            id_empleado    BIGINT                DEFAULT NULL,
            accion         VARCHAR(20)  NOT NULL,  -- emitido|aceptado|rechazado|anulado|expirado|requiere_firma
            usuario        VARCHAR(120)          DEFAULT NULL,
            ip             VARCHAR(64)           DEFAULT NULL,
            hash_documental CHAR(64)             DEFAULT NULL,
            version_doc    INT          NOT NULL DEFAULT 1,
            detalle        VARCHAR(255)          DEFAULT NULL,
            fecha_hora     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_aud_doc (id_documento),
            INDEX idx_aud_empresa (id_empresa, accion),
            CONSTRAINT fk_aud_doc FOREIGN KEY (id_documento)
                REFERENCES rrhh_documentos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS rrhh_doc_auditoria")
    cur.execute("ALTER TABLE rrhh_documentos DROP INDEX IF EXISTS idx_doc_firma")
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE rrhh_documentos DROP COLUMN IF EXISTS {col}")
