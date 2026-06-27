"""
Migracion 0065 — BI Corporativo (Data Warehouse + OLAP). ADITIVA, idempotente, reversible.

NO toca el BI existente (bi_kpi_def/bi_kpi_valores/bi_snapshots permanecen). Anade una capa DW
DESACOPLADA: tabla de hechos unica multidominio (mas escalable que 11 tablas casi identicas),
dimensiones corporativas y log de ETL. Multiempresa/tienda/almacen.
"""

VERSION = "0065"
DESCRIPCION = "BI Corporativo: dw_hechos (DW unificado), dw_dimensiones, dw_etl_ejecuciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── FASE A · Data Warehouse (tabla de hechos unificada) ───────────────────
    ("dw_hechos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        id_almacen INT NOT NULL DEFAULT 0,
        dominio VARCHAR(20) NOT NULL,
        metrica VARCHAR(60) NOT NULL,
        valor DECIMAL(20,4) NOT NULL DEFAULT 0,
        granularidad VARCHAR(10) NOT NULL DEFAULT 'mensual',
        periodo VARCHAR(10) NOT NULL,
        fecha DATE NOT NULL,
        dims TEXT DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_dw (id_empresa, id_tienda, id_almacen, dominio, metrica, granularidad, periodo),
        INDEX idx_dw_dom (id_empresa, dominio, periodo),
        INDEX idx_dw_fecha (fecha)"""),
    # ── FASE B · Dimensiones corporativas (catalogo OLAP) ─────────────────────
    ("dw_dimensiones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        dimension VARCHAR(20) NOT NULL,
        clave VARCHAR(64) NOT NULL,
        valor VARCHAR(200) DEFAULT NULL,
        padre VARCHAR(64) DEFAULT NULL,
        UNIQUE KEY uq_dim (id_empresa, dimension, clave),
        INDEX idx_dim (id_empresa, dimension)"""),
    # ── ETL ────────────────────────────────────────────────────────────────────
    ("dw_etl_ejecuciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        dominio VARCHAR(20) DEFAULT NULL,
        granularidad VARCHAR(10) DEFAULT NULL,
        periodo VARCHAR(10) DEFAULT NULL,
        filas INT NOT NULL DEFAULT 0,
        estado VARCHAR(12) NOT NULL DEFAULT 'ok',
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_etl (id_empresa, dominio, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
