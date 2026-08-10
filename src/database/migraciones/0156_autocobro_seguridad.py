"""
Migración 0156 — Auditoría de seguridad del autocobro (Capa 3). ADITIVA, idempotente, reversible.

Capa 3 (de la caja al ERP): cuando termina una venta de autocobro se registran los METADATOS DE
SEGURIDAD junto a la transacción (nº de intervenciones de peso, anulaciones, quién autorizó, duración),
y se guarda cada INCIDENCIA por artículo (bloqueo de peso / anulación) para la analítica de merma y la
optimización del máster de productos (detectar packaging cambiado por el proveedor).

  · autocobro_seguridad_log  — un registro por venta: resumen de seguridad (el "security_logs" del ticket).
  · autocobro_incidencias    — un registro por incidencia de artículo (para "artículos conflictivos").

Multiempresa/multitienda (clave por id_empresa/id_tienda). No crea motor nuevo: es persistencia de
auditoría que alimenta BI/Merma existentes.
"""

VERSION = "0156"
DESCRIPCION = "Autocobro: security_logs por venta (autocobro_seguridad_log) + incidencias por artículo"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("autocobro_seguridad_log", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(64) DEFAULT NULL,
        id_tienda VARCHAR(64) DEFAULT NULL,
        terminal_id VARCHAR(60) DEFAULT NULL,
        venta_id INT DEFAULT NULL,
        intervenciones_peso INT NOT NULL DEFAULT 0,
        anulaciones INT NOT NULL DEFAULT 0,
        autorizado_por VARCHAR(100) DEFAULT NULL,
        duracion_seg INT NOT NULL DEFAULT 0,
        items INT NOT NULL DEFAULT 0,
        total DECIMAL(10,2) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_asl_emp (id_empresa, id_tienda, creado),
        INDEX idx_asl_venta (venta_id)
    """),
    ("autocobro_incidencias", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(64) DEFAULT NULL,
        id_tienda VARCHAR(64) DEFAULT NULL,
        terminal_id VARCHAR(60) DEFAULT NULL,
        venta_id INT DEFAULT NULL,
        codigo_articulo VARCHAR(60) DEFAULT NULL,
        nombre VARCHAR(255) DEFAULT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'BLOQUEO_PESO',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ai_emp (id_empresa, id_tienda, creado),
        INDEX idx_ai_art (id_empresa, codigo_articulo, tipo)
    """),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                    f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
