"""
Migración 0164 — Cierre H1 (Fase 12): columnas de STORAGE en `documentos_registro`. ADITIVA, no destructiva,
compatible hacia atrás. No crea tabla nueva ni motor de documentos paralelo: amplía el índice documental
existente para referenciar el objeto en `StorageProvider`/S3 y su estado de migración.

Columnas: storage_key (clave tenant-aware en el StorageProvider), storage_backend (local|s3),
mime_type, size_bytes, migracion_estado (LEGACY|MIGRATED|MISSING|FAILED). Los documentos previos quedan como
LEGACY hasta que se migren (backfill idempotente). Aislado por tenant (id_empresa ya existe en la tabla).
"""

VERSION = "0164"
DESCRIPCION = "Documentos: storage_key/backend/mime/size/migracion_estado en documentos_registro (H1 AWS)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [
    ("storage_key", "VARCHAR(500) DEFAULT NULL"),
    ("storage_backend", "VARCHAR(20) DEFAULT NULL"),
    ("mime_type", "VARCHAR(120) DEFAULT NULL"),
    ("size_bytes", "BIGINT DEFAULT NULL"),
    ("migracion_estado", "VARCHAR(20) NOT NULL DEFAULT 'LEGACY'"),
]


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n) > 0


def aplicar(cur):
    # Idempotente: añade cada columna sólo si no existe (evita error al reaplicar).
    for col, tipo in _COLS:
        if not _tiene_columna(cur, "documentos_registro", col):
            cur.execute(f"ALTER TABLE documentos_registro ADD COLUMN {col} {tipo}")
    if not _tiene_columna(cur, "documentos_registro", "storage_key"):
        return
    try:
        cur.execute("CREATE INDEX idx_doc_storage_key ON documentos_registro (storage_key)")
    except Exception:
        pass   # el índice ya existe
    try:
        cur.execute("CREATE INDEX idx_doc_migracion ON documentos_registro (id_empresa, migracion_estado)")
    except Exception:
        pass


def revertir(cur):
    for col, _ in _COLS:
        try:
            cur.execute(f"ALTER TABLE documentos_registro DROP COLUMN {col}")
        except Exception:
            pass
