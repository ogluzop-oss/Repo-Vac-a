"""
Migracion 0105 — Enriquecimiento de Almacenes (Módulo 5). ADITIVA, idempotente, reversible.
Auditoría: pasillo/estantería/balda/nivel + ubicaciones (tienda y almacén) + mapa ya existen en
`ubicaciones`. Se añade SOLO lo ausente: zona/capacidad/restricciones por ubicación y las tablas de
picking/packing (con soporte de cross-docking y consolidación en el servicio). No duplica: reutiliza
`ubicaciones` y los pedidos existentes.
"""

VERSION = "0105"
DESCRIPCION = "Almacenes: zona/capacidad/restricciones + picking/packing"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLUMNAS = [
    ("ubicaciones", "zona", "VARCHAR(40) DEFAULT NULL"),
    ("ubicaciones", "capacidad", "INT DEFAULT NULL"),
    ("ubicaciones", "restriccion", "VARCHAR(120) DEFAULT NULL"),
]

_TABLAS = [
    ("almacen_picking", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        referencia VARCHAR(80) DEFAULT NULL,
        origen VARCHAR(40) DEFAULT 'pedido',
        id_documento VARCHAR(64) DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
        cross_docking TINYINT NOT NULL DEFAULT 0,
        responsable VARCHAR(80) DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_picking (id_empresa, estado)"""),
    ("almacen_picking_lineas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_picking INT NOT NULL,
        codigo_articulo VARCHAR(64) DEFAULT NULL,
        cantidad DECIMAL(14,3) NOT NULL DEFAULT 0,
        ubicacion VARCHAR(80) DEFAULT NULL,
        pickeado DECIMAL(14,3) NOT NULL DEFAULT 0,
        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
        INDEX idx_pickln (id_picking)"""),
]


def _existe(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for tabla, col, definicion in _COLUMNAS:
        if not _existe(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for tabla, col, _ in reversed(_COLUMNAS):
        if _existe(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
