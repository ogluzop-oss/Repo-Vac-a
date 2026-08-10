"""
Migracion 0122 — IOC v2.0 · Bloque 1: Fundamentos de Identidad Corporativa. ADITIVA, idempotente,
reversible. Convierte IOC en el Identity Core: añade el nivel superior de la jerarquía (grupo
empresarial), el gobierno de identidad (estados oficiales, propiedad, niveles jerárquicos) y la
auditoría enriquecida de identidad (valor anterior/nuevo, IP, terminal). NO duplica entidades:
reutiliza `empresas` y `centros_trabajo` (extendidos aditivamente). NO borra nada (soft delete).
"""

VERSION = "0122"
DESCRIPCION = "IOC v2 B1: grupos empresariales + gobierno de identidad + niveles + auditoría identidad"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ioc_grupos_empresariales", """
        id CHAR(36) NOT NULL PRIMARY KEY,
        nombre VARCHAR(200) NOT NULL,
        nombre_corto VARCHAR(60) DEFAULT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'GRUPO',
        estado_gobierno VARCHAR(24) NOT NULL DEFAULT 'ACTIVO',
        id_propietario VARCHAR(80) DEFAULT NULL,
        usuario_creador VARCHAR(80) DEFAULT NULL,
        usuario_modificacion VARCHAR(80) DEFAULT NULL,
        observaciones TEXT DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_modificacion DATETIME DEFAULT NULL,
        INDEX idx_grupo_estado (estado_gobierno)"""),
    ("ioc_identidad_auditoria", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        entidad_tipo VARCHAR(24) NOT NULL,
        entidad_id VARCHAR(36) NOT NULL,
        campo VARCHAR(60) DEFAULT NULL,
        valor_anterior TEXT DEFAULT NULL,
        valor_nuevo TEXT DEFAULT NULL,
        accion VARCHAR(40) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        ip VARCHAR(45) DEFAULT NULL,
        id_terminal CHAR(36) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ident_audit (entidad_tipo, entidad_id, fecha)"""),
]

_COLUMNAS = [
    # Nivel superior de la jerarquía: la empresa puede pertenecer a un grupo/holding/franquicia.
    ("empresas", "id_grupo", "CHAR(36) DEFAULT NULL"),
    # Gobierno de identidad sobre la entidad de centro existente.
    ("centros_trabajo", "nivel", "VARCHAR(20) NOT NULL DEFAULT 'CENTRO'"),
    ("centros_trabajo", "estado_gobierno", "VARCHAR(24) NOT NULL DEFAULT 'ACTIVO'"),
    ("centros_trabajo", "id_propietario", "VARCHAR(80) DEFAULT NULL"),
    ("centros_trabajo", "id_responsable_operativo", "VARCHAR(80) DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna):
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def _existe_tabla(cur, tabla):
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s", (tabla,))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for tabla, col, definicion in _COLUMNAS:
        if _existe_tabla(cur, tabla) and not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
    for tabla, col, _ in reversed(_COLUMNAS):
        try:
            if _existe_tabla(cur, tabla) and _existe_columna(cur, tabla, col):
                cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
        except Exception:
            pass
