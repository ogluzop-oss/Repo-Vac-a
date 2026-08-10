"""
Migracion 0091 — Actividad avanzada: favoritos y seguimiento (Paquete Enterprise 2). ADITIVA,
idempotente, reversible. NO toca ninguna tabla existente. Solo estado NUEVO por usuario (marcar
favorito / seguir un evento); no duplica datos del ERP. Multiempresa/multitienda.
"""

VERSION = "0091"
DESCRIPCION = "Actividad avanzada: actividad_favoritos, actividad_seguidos"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("actividad_favoritos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        usuario VARCHAR(80) NOT NULL,
        id_evento BIGINT NOT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_fav (id_empresa, usuario, id_evento),
        INDEX idx_fav (id_empresa, usuario)"""),

    ("actividad_seguidos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        usuario VARCHAR(80) NOT NULL,
        id_evento BIGINT DEFAULT NULL,
        ref_entidad VARCHAR(60) DEFAULT NULL,
        ref_id VARCHAR(80) DEFAULT NULL,
        ultimo_id_visto BIGINT NOT NULL DEFAULT 0,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_seg (id_empresa, usuario, ref_entidad, ref_id),
        INDEX idx_seg (id_empresa, usuario)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
