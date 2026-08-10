"""
Migracion 0101 — Jobs Enterprise Opt-In (Bloque 1). ADITIVA, idempotente, reversible. Extiende
`scheduler_jobs` con la configuración editable por empresa (prioridad, timeout, reintentos, categoría
y una marca `configurado` para respetar los cambios del usuario frente a la sincronización del
catálogo) y `scheduler_historial` con la duración medida. No crea tablas nuevas: reutiliza el
Scheduler existente (COM-3).
"""

VERSION = "0101"
DESCRIPCION = "Jobs Opt-In: config editable en scheduler_jobs + duración en historial"
REVERSIBLE = True
REQUIERE_BACKUP = False

# (tabla, columna, definición) — se añaden solo si no existen.
_COLUMNAS = [
    ("scheduler_jobs", "prioridad", "VARCHAR(10) NOT NULL DEFAULT 'normal'"),
    ("scheduler_jobs", "timeout_seg", "INT NOT NULL DEFAULT 300"),
    ("scheduler_jobs", "max_reintentos", "INT NOT NULL DEFAULT 1"),
    ("scheduler_jobs", "categoria", "VARCHAR(40) DEFAULT NULL"),
    ("scheduler_jobs", "pesado", "TINYINT NOT NULL DEFAULT 0"),
    ("scheduler_jobs", "configurado", "TINYINT NOT NULL DEFAULT 0"),
    ("scheduler_jobs", "id_tienda", "INT DEFAULT NULL"),
    ("scheduler_historial", "duracion_ms", "INT DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for tabla, col, definicion in _COLUMNAS:
        if not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for tabla, col, _ in reversed(_COLUMNAS):
        if _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
