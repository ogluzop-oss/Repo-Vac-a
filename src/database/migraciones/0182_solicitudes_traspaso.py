"""
Migración 0182 — Solicitudes de traspaso al almacén central (LOGÍSTICA). ADITIVA, idempotente, reversible.

Permite que una tienda PIDA mercancía al almacén central desde la función de recepción. La solicitud (cabecera
+ líneas) se sirve moviendo stock central→tienda por el motor oficial `db/stock_almacen.traspasar_stock`
(kárdex TRASPASO). AISLAMIENTO por `id_empresa`.
"""

VERSION = "0182"
DESCRIPCION = "Logística: solicitudes de traspaso al almacén central (cabecera + líneas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("solicitudes_traspaso", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_tienda INT DEFAULT NULL,
        almacen_origen BIGINT NOT NULL,
        almacen_destino BIGINT NOT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'PENDIENTE',
        usuario VARCHAR(80) DEFAULT NULL,
        observaciones VARCHAR(255) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        servido DATETIME DEFAULT NULL,
        INDEX idx_sol_emp (id_empresa, estado)"""),
    ("solicitudes_traspaso_items", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_solicitud BIGINT NOT NULL,
        codigo_articulo VARCHAR(64) NOT NULL,
        cantidad_solicitada INT NOT NULL DEFAULT 0,
        cantidad_servida INT NOT NULL DEFAULT 0,
        INDEX idx_sol_item (id_solicitud)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
