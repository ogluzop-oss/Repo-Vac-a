"""
Migración 0209 — Watchlist de artículos monitorizados (módulo Proveedores, Fase 3). ADITIVA, idempotente,
reversible. Lista de artículos que la empresa vigila para detectar variaciones de coste (índice de mercado).
"""

VERSION = "0209"
DESCRIPCION = "Watchlist de artículos monitorizados (compras_watchlist)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("compras_watchlist", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        codigo_articulo VARCHAR(50) NOT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_wl (id_empresa, codigo_articulo),
        INDEX idx_wl_emp (id_empresa)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
