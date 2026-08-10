"""
Migracion 0121 — Identidad Operativa de Centros (IOC). ADITIVA, idempotente, reversible.

Evoluciona la primitiva «Asignar referencia» (configuraciones.ref_tienda/ref_almacen, que se
CONSERVAN — patrón Strangler) hacia una infraestructura central de identidad. NO duplica la entidad
de centro existente (`centros_trabajo`): la EXTIENDE con los atributos de identidad ausentes (tipo,
nombre corto, alias, centro padre, archivado, observaciones, usuarios y fecha de modificación) y
añade tablas satélite para lo genuinamente ausente:
  · `ioc_centro_codigos`  — códigos operativos MÚLTIPLES e INDEPENDIENTES por centro.
  · `ioc_terminales`      — identidad propia de cada TPV/PDA/dispositivo (UUID, MAC, IP, sw…).
  · `ioc_impresoras`      — registro de impresoras vinculadas a centro/terminal/empresa.
Todo multiempresa (por id_empresa). No reescribe centros_trabajo/tiendas/almacen.
"""

VERSION = "0121"
DESCRIPCION = "Identidad Operativa de Centros: centros_trabajo extendido + códigos/terminales/impresoras"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ioc_centro_codigos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_centro CHAR(36) NOT NULL,
        tipo_codigo VARCHAR(20) NOT NULL,
        valor VARCHAR(80) NOT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        UNIQUE KEY uq_centro_codigo (id_centro, tipo_codigo),
        INDEX idx_ioc_cod (id_empresa, tipo_codigo, valor)"""),
    ("ioc_terminales", """
        id CHAR(36) NOT NULL PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_centro CHAR(36) DEFAULT NULL,
        codigo_terminal VARCHAR(60) DEFAULT NULL,
        tipo_dispositivo VARCHAR(30) NOT NULL DEFAULT 'TPV',
        nombre VARCHAR(120) DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
        ultima_conexion DATETIME DEFAULT NULL,
        version_sw VARCHAR(40) DEFAULT NULL,
        ultima_sync DATETIME DEFAULT NULL,
        ip VARCHAR(45) DEFAULT NULL,
        mac VARCHAR(32) DEFAULT NULL,
        sistema_operativo VARCHAR(60) DEFAULT NULL,
        numero_serie VARCHAR(80) DEFAULT NULL,
        observaciones VARCHAR(255) DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        archivado TINYINT NOT NULL DEFAULT 0,
        fecha_alta DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_modificacion DATETIME DEFAULT NULL,
        INDEX idx_term (id_empresa, id_centro, estado),
        INDEX idx_term_cod (id_empresa, codigo_terminal)"""),
    ("ioc_impresoras", """
        id CHAR(36) NOT NULL PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_centro CHAR(36) DEFAULT NULL,
        id_terminal CHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) DEFAULT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'TICKETS',
        nombre VARCHAR(120) DEFAULT NULL,
        backend VARCHAR(40) DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
        activo TINYINT NOT NULL DEFAULT 1,
        archivado TINYINT NOT NULL DEFAULT 0,
        observaciones VARCHAR(255) DEFAULT NULL,
        fecha_alta DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_modificacion DATETIME DEFAULT NULL,
        INDEX idx_impr (id_empresa, id_centro, tipo)"""),
]

# Columnas de identidad AÑADIDAS a la entidad de centro existente (no se duplica la tabla).
_COLUMNAS = [
    ("centros_trabajo", "tipo", "VARCHAR(30) NOT NULL DEFAULT 'OTRO'"),
    ("centros_trabajo", "nombre_corto", "VARCHAR(60) DEFAULT NULL"),
    ("centros_trabajo", "alias", "VARCHAR(120) DEFAULT NULL"),
    ("centros_trabajo", "id_centro_padre", "CHAR(36) DEFAULT NULL"),
    ("centros_trabajo", "archivado", "TINYINT NOT NULL DEFAULT 0"),
    ("centros_trabajo", "observaciones", "TEXT DEFAULT NULL"),
    ("centros_trabajo", "usuario_creador", "VARCHAR(80) DEFAULT NULL"),
    ("centros_trabajo", "usuario_modificacion", "VARCHAR(80) DEFAULT NULL"),
    ("centros_trabajo", "fecha_modificacion", "DATETIME DEFAULT NULL"),
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
    # Extensión aditiva de la entidad de centro existente (solo si la tabla existe ya).
    if _existe_tabla(cur, "centros_trabajo"):
        for tabla, col, definicion in _COLUMNAS:
            if not _existe_columna(cur, tabla, col):
                cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
    if _existe_tabla(cur, "centros_trabajo"):
        for tabla, col, _ in reversed(_COLUMNAS):
            try:
                if _existe_columna(cur, tabla, col):
                    cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
            except Exception:
                pass
