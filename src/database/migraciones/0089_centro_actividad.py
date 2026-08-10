"""
Migracion 0089 — Centro de Actividad Empresarial (Fase 3). ADITIVA, idempotente, reversible.

NO toca ninguna tabla existente. Solo crea `actividad_vistas`: una marca de agua (watermark)
por usuario y modulo con la fecha de la ultima vez que el usuario ATENDIO ese modulo. Los
badges NO se almacenan como numero: se CALCULAN al vuelo contando eventos posteriores a esta
marca (desde la cola de eventos, Fase 1). Multiempresa/multitienda.
"""

VERSION = "0089"
DESCRIPCION = "Centro de Actividad: actividad_vistas (watermark de lectura por usuario/modulo)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("actividad_vistas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        usuario VARCHAR(80) NOT NULL,
        modulo VARCHAR(40) NOT NULL,
        ultima_vista DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_actvista (id_empresa, usuario, modulo),
        INDEX idx_actvista (id_empresa, usuario)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
