"""
Migración 0188 — Transporte / Flota + rutas de reparto (función base `transporte.reparto`, R8). ADITIVA, reversible.

Flota de vehículos y rutas de reparto con paradas y líneas. Al ENTREGAR una parada, la mercancía sale del
stock por la política ÚNICA (`db/salida_stock`) + kárdex `SALIDA_REPARTO` (idempotente). AISLAMIENTO por
`id_empresa`. El vehículo puede vincularse a un activo GMAO (`id_activo`) para su mantenimiento.
"""

VERSION = "0188"
DESCRIPCION = "Transporte: vehículos + rutas + paradas + líneas (reparto con salida de stock oficial)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("transporte_vehiculos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        matricula VARCHAR(24) DEFAULT NULL,
        descripcion VARCHAR(160) DEFAULT NULL,
        capacidad_kg INT DEFAULT NULL,
        conductor VARCHAR(120) DEFAULT NULL,
        id_activo BIGINT DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'activo',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_tvh (id_empresa, estado)"""),
    ("transporte_rutas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        fecha DATE DEFAULT NULL,
        id_vehiculo BIGINT DEFAULT NULL,
        conductor VARCHAR(120) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'planificada',
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_trt (id_empresa, fecha)"""),
    ("transporte_paradas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_ruta BIGINT NOT NULL,
        id_empresa CHAR(36) DEFAULT NULL,
        orden INT NOT NULL DEFAULT 0,
        cliente VARCHAR(160) DEFAULT NULL,
        direccion VARCHAR(240) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'pendiente',
        entregado DATETIME DEFAULT NULL,
        INDEX idx_tpa (id_ruta, orden)"""),
    ("transporte_paradas_lineas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_parada BIGINT NOT NULL,
        id_empresa CHAR(36) DEFAULT NULL,
        codigo_articulo VARCHAR(64) NOT NULL,
        cantidad INT NOT NULL DEFAULT 0,
        entregado INT NOT NULL DEFAULT 0,
        INDEX idx_tpl (id_parada)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
