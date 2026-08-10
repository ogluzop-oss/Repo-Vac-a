"""
Migración 0135 — Fase V · Bloque 3 API Pública para terceros. ADITIVA, idempotente, reversible.

Aplicaciones de desarrollador (OAuth2 client credentials) para integraciones oficiales externas.
Multiempresa (cada app pertenece a una empresa). No modifica la REST API existente.
"""

VERSION = "0135"
DESCRIPCION = "Fase V · API Pública: aplicaciones de desarrollador (OAuth2)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("api_dev_apps", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        client_id VARCHAR(48) NOT NULL,
        client_secret_hash VARCHAR(128) NOT NULL,
        scopes TEXT DEFAULT NULL,
        sandbox TINYINT NOT NULL DEFAULT 1,
        estado VARCHAR(16) NOT NULL DEFAULT 'activa',   -- activa|suspendida|revocada
        redirect_uri VARCHAR(500) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_client (client_id),
        INDEX idx_app (id_empresa, estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
