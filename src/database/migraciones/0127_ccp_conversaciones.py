"""
Migración 0127 — CCP Fase II · B4 Communication Timeline + Conversation. ADITIVA, idempotente,
reversible.

Añade el concepto de CONVERSATION (hilo que agrupa comunicaciones relacionadas) y enlaza cada
comunicación a su hilo mediante `conversation_id` en `ccp_comunicaciones`. Multiempresa.
"""

VERSION = "0127"
DESCRIPCION = "CCP II · Conversaciones (hilos) + conversation_id en ccp_comunicaciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ccp_conversaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        entidad_tipo VARCHAR(30) DEFAULT NULL,
        entidad_id VARCHAR(64) DEFAULT NULL,
        correo VARCHAR(255) DEFAULT NULL,
        asunto VARCHAR(255) DEFAULT NULL,
        canales VARCHAR(120) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'abierta',
        n_mensajes INT NOT NULL DEFAULT 0,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_ccp_conv (id_empresa, correo),
        INDEX idx_ccp_conv_ent (id_empresa, entidad_tipo, entidad_id)"""),
]
_COLUMNAS = [
    ("ccp_comunicaciones", "conversation_id", "BIGINT DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna):
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def _existe_tabla(cur, tabla):
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s", (tabla,))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for tabla, col, definicion in _COLUMNAS:
        if _existe_tabla(cur, tabla) and not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for tabla, col, _ in _COLUMNAS:
        if _existe_tabla(cur, tabla) and _existe_columna(cur, tabla, col):
            try:
                cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
            except Exception:
                pass
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
