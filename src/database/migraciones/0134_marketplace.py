"""
Migración 0134 — Fase IV · Bloque 2 Marketplace Corporativo. ADITIVA, idempotente, reversible.

Amplía el Plugin SDK (plugins_instalados, migr 0132) SIN modificarlo: repositorios, política por
empresa, licencias e historial de versiones (para rollback). Multiempresa (id_empresa NULL = global).
"""

VERSION = "0134"
DESCRIPCION = "Fase IV · Marketplace: repositorios, política, licencias, historial de plugins"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("marketplace_repositorios", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        nombre VARCHAR(120) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'local',   -- oficial|privado|git|zip|local
        url VARCHAR(500) DEFAULT NULL,
        prioridad INT NOT NULL DEFAULT 100,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_repo (id_empresa, nombre),
        INDEX idx_repo (tipo, activo)"""),
    ("marketplace_politica", """
        id_empresa CHAR(36) NOT NULL PRIMARY KEY,
        politica VARCHAR(16) NOT NULL DEFAULT 'firmados',  -- oficiales|firmados|internos|todos
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP"""),
    ("marketplace_licencias", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        clave_plugin VARCHAR(80) NOT NULL,
        tipo VARCHAR(16) NOT NULL DEFAULT 'empresa',  -- empresa|tienda|usuario|temporal|enterprise
        alcance_id VARCHAR(64) DEFAULT NULL,          -- id_tienda / id_usuario según tipo
        valido_desde DATETIME DEFAULT CURRENT_TIMESTAMP,
        valido_hasta DATETIME DEFAULT NULL,           -- NULL = perpetua
        estado VARCHAR(16) NOT NULL DEFAULT 'activa', -- activa|revocada|caducada
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_lic (id_empresa, clave_plugin, estado)"""),
    ("plugins_historial", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        clave VARCHAR(80) NOT NULL,
        version VARCHAR(20) DEFAULT NULL,
        accion VARCHAR(16) NOT NULL,                  -- instalar|actualizar|desinstalar|rollback
        manifest MEDIUMTEXT DEFAULT NULL,
        ruta VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_hist (id_empresa, clave, creado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
