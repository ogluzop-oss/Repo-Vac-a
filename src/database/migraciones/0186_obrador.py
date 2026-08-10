"""
Migración 0186 — Obrador / producción diaria (edición Bakery). ADITIVA, idempotente, reversible.

Parte de producción del obrador: qué se ha elaborado en el día (productos terminados + cantidades). Al
registrarlo, se produce el terminado (stock vendible + kárdex ENTRADA_PRODUCCION) y, si el producto tiene BOM,
se consumen los ingredientes por la salida de stock OFICIAL (kárdex/FEFO). AISLAMIENTO por `id_empresa`.
"""

VERSION = "0186"
DESCRIPCION = "Bakery: obrador_partes + obrador_partes_lineas (producción diaria)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("obrador_partes", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        fecha DATE DEFAULT NULL,
        turno VARCHAR(24) DEFAULT NULL,
        responsable VARCHAR(120) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'registrado',
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_obr (id_empresa, fecha)"""),
    ("obrador_partes_lineas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_parte BIGINT NOT NULL,
        codigo_articulo VARCHAR(64) NOT NULL,
        cantidad INT NOT NULL DEFAULT 0,
        INDEX idx_obr_lin (id_parte)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
