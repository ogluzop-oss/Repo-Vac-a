"""
Migración 0144 — PCD · Etapa B · Fase B2: estado de sincronización (watermark incremental).

Guarda el cursor por (empresa, canal) para la sincronización INCREMENTAL, y las marcas de la última
sync completa/incremental. Reutiliza el Sync Engine existente (no crea motor nuevo).

ADITIVA, idempotente, reversible. No elimina ni altera datos.
"""

VERSION = "0144"
DESCRIPCION = "PCD Etapa B/F2: cd_sync_estado (watermark de sincronización incremental)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_sync_estado", """
        id                 BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa         CHAR(36)             DEFAULT NULL,
        canal              VARCHAR(40) NOT NULL,
        watermark          VARCHAR(160)         DEFAULT NULL,   -- cursor incremental (ts/id externo)
        ultimo_full        DATETIME             DEFAULT NULL,
        ultimo_incremental DATETIME             DEFAULT NULL,
        items_totales      BIGINT      NOT NULL DEFAULT 0,
        ts_actualizado     DATETIME             DEFAULT NULL,
        UNIQUE KEY uq_sync_estado (id_empresa, canal),
        INDEX idx_sync_estado_canal (canal)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
