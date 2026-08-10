"""
Migración 0180 — Histórico de ventas IMPORTADO (para forecasting). ADITIVA, idempotente, reversible.

`ventas_historicas` guarda series de ventas ANTERIORES a Smart Manager, SOLO para alimentar la predicción. NO
es la tabla operativa `ventas` (no afecta a caja/contabilidad/informes financieros): integridad fiscal intacta.
AISLAMIENTO por `id_empresa`. UNIQUE(id_empresa, fecha, codigo) → re-importar ACTUALIZA (idempotente).
"""

VERSION = "0180"
DESCRIPCION = "Histórico de ventas importado (ventas_historicas) para forecasting — no toca `ventas`"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = """
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_empresa CHAR(36) DEFAULT NULL,
    fecha DATE NOT NULL,
    codigo_articulo VARCHAR(64) NOT NULL,
    cantidad DECIMAL(14,3) NOT NULL DEFAULT 0,
    importe DECIMAL(14,2) NOT NULL DEFAULT 0,
    origen VARCHAR(24) NOT NULL DEFAULT 'importacion',
    creado DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_vh (id_empresa, fecha, codigo_articulo),
    INDEX idx_vh (id_empresa, fecha)"""


def aplicar(cur):
    cur.execute(f"CREATE TABLE IF NOT EXISTS ventas_historicas ({_COLS}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS ventas_historicas")
