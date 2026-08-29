"""
Migración 0229 — Métricas de visibilidad del catálogo B2B: vistas/clics (Smart Suppliers B2B · Fase 3).

Un evento por artículo/empresa/tipo/día (UNIQUE + INSERT IGNORE en el servicio): recargar la misma
página de catálogo el mismo día no duplica filas, acotando el crecimiento de la tabla sin perder
granularidad diaria. ADITIVA, idempotente, reversible.
"""

VERSION = "0229"
DESCRIPCION = "Eventos de vista/clic del catálogo B2B (métricas de visibilidad del proveedor)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = ("b2b_catalogo_eventos", """
    id          BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_articulo BIGINT      NOT NULL,
    id_empresa  CHAR(36)    NOT NULL,
    tipo        ENUM('vista','click') NOT NULL,
    fecha       DATE        NOT NULL,
    creado_en   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_b2b_evento (id_articulo, id_empresa, tipo, fecha),
    INDEX idx_b2b_evento_articulo (id_articulo)""")


def aplicar(cur):
    nombre, cols = _TABLA
    cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute(f"DROP TABLE IF EXISTS {_TABLA[0]}")
