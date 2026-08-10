"""
Migración 0185 — Recetas y dispensación (edición Pharmacy). ADITIVA, idempotente, reversible.

Una receta (cabecera + líneas de medicamento/posología) para un paciente; al DISPENSARLA se descuenta el stock
por el motor OFICIAL de salida (`db/salida_stock` → clamp + kárdex + FEFO). NO crea venta/factura (la facturación
va por el flujo normal si procede). AISLAMIENTO por `id_empresa`.
"""

VERSION = "0185"
DESCRIPCION = "Pharmacy: recetas + recetas_lineas (dispensación con salida de stock oficial)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("recetas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        paciente VARCHAR(160) NOT NULL,
        cliente_id BIGINT DEFAULT NULL,
        medico VARCHAR(160) DEFAULT NULL,
        fecha DATE DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'PENDIENTE',
        observaciones VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        dispensado DATETIME DEFAULT NULL,
        INDEX idx_rx (id_empresa, estado)"""),
    ("recetas_lineas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_receta BIGINT NOT NULL,
        codigo_articulo VARCHAR(64) NOT NULL,
        cantidad INT NOT NULL DEFAULT 1,
        posologia VARCHAR(160) DEFAULT NULL,
        dispensado INT NOT NULL DEFAULT 0,
        INDEX idx_rx_lin (id_receta)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
