"""
Migración 0219 — Smart Suppliers · Fase A: catálogo B2B del proveedor. ADITIVA, idempotente, reversible.

`unidad_medida` es obligatoria en el alta (validada en el servicio, no en la BD, para poder dar un
mensaje de error claro) — mayorista: kg/unidad/palé/caja. `moq` = cantidad mínima de pedido.
`b2b_catalogo_import_lotes` audita cada subida masiva (fila a fila, con errores) para poder mostrar al
proveedor qué se importó y qué no, sin adivinar silenciosamente.
"""

VERSION = "0219"
DESCRIPCION = "Smart Suppliers: catálogo B2B (unidad mayorista + MOQ) + auditoría de import masivo"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("b2b_catalogo", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_suministrador BIGINT NOT NULL,
        codigo VARCHAR(50) NOT NULL,
        nombre VARCHAR(255) NOT NULL,
        descripcion TEXT DEFAULT NULL,
        unidad_medida VARCHAR(20) NOT NULL DEFAULT 'unidad',
        moq INT NOT NULL DEFAULT 1,
        precio_unitario DECIMAL(12,4) NOT NULL DEFAULT 0,
        sector_id INT DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        actualizado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_b2bcat_sum_codigo (id_suministrador, codigo),
        INDEX idx_b2bcat_sector (sector_id), INDEX idx_b2bcat_activo (activo)"""),
    ("b2b_catalogo_import_lotes", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_suministrador BIGINT NOT NULL,
        archivo_nombre VARCHAR(255) DEFAULT NULL,
        filas_ok INT NOT NULL DEFAULT 0,
        filas_error INT NOT NULL DEFAULT 0,
        detalle_errores MEDIUMTEXT DEFAULT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_lote_sum (id_suministrador)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
