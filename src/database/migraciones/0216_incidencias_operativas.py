"""
Migración 0216 — Incidencias OPERATIVAS de tienda/almacén. ADITIVA, idempotente, reversible.

Dominio nuevo y DISTINTO de `incidentes_seguridad` (migración de seguridad/auditoría: fuerza bruta,
token comprometido, acceso sospechoso — ver `src/services/seguridad/incidentes.py`). Esta tabla es
para el personal de tienda/almacén: roturas, limpieza, averías de equipo, incidencias con clientes,
etc., reportadas típicamente desde el cliente móvil. Multiempresa por `id_empresa`.
"""

VERSION = "0216"
DESCRIPCION = "Incidencias operativas de tienda/almacén (distintas de incidentes de seguridad)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("incidencias_operativas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        tipo VARCHAR(40) NOT NULL DEFAULT 'otro',
        titulo VARCHAR(160) NOT NULL,
        descripcion TEXT DEFAULT NULL,
        prioridad VARCHAR(10) NOT NULL DEFAULT 'normal',
        estado VARCHAR(12) NOT NULL DEFAULT 'abierta',
        ubicacion VARCHAR(120) DEFAULT NULL,
        reportado_por INT DEFAULT NULL,
        asignado_a INT DEFAULT NULL,
        ref_entidad VARCHAR(40) DEFAULT NULL,
        ref_id VARCHAR(64) DEFAULT NULL,
        resolucion TEXT DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_cierre DATETIME DEFAULT NULL,
        INDEX idx_inc_op_estado (id_empresa, estado),
        INDEX idx_inc_op_rep (id_empresa, reportado_por),
        INDEX idx_inc_op_asig (id_empresa, asignado_a)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
