"""
Migracion 0090 — Transporte fisico, replicacion y operacion distribuida (Fase 4). ADITIVA,
idempotente, reversible. NO toca ninguna tabla existente. Reutiliza edge_nodes (terminales),
distribucion_pendiente/confirmaciones (Fase 2) y eventos (Fase 1). Multiempresa/multitienda.

Crea:
  • sync_paquetes        → paquetes DIFERENCIALES comprimidos (altas/bajas/modif), con offset
                           de reanudacion (SUBFASE 4.3/4.4/4.5).
  • terminal_versiones   → version SW/BD, ultima sync, ultimo paquete, revision, hash (4.7).
  • sync_sesiones        → observabilidad: inicio/fin/duracion/bytes/nº eventos/origen/destino (4.13).
  • sync_actualizaciones → manifiesto de actualizaciones (canal normal/emergencia, hash, firma) (4.8/4.9).
Preparado para millones de paquetes (indices por empresa/estado/fecha).
"""

VERSION = "0090"
DESCRIPCION = "Sync Fase 4: sync_paquetes, terminal_versiones, sync_sesiones, sync_actualizaciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("sync_paquetes", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        uuid CHAR(36) NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        origen_tienda INT NOT NULL DEFAULT 0,
        destino_tienda INT NOT NULL DEFAULT 0,
        tipo VARCHAR(12) NOT NULL DEFAULT 'diff',
        prioridad VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        num_eventos INT NOT NULL DEFAULT 0,
        bytes INT NOT NULL DEFAULT 0,
        bytes_comprimido INT NOT NULL DEFAULT 0,
        hash VARCHAR(64) DEFAULT NULL,
        contenido MEDIUMBLOB DEFAULT NULL,
        offset_aplicado INT NOT NULL DEFAULT 0,
        estado VARCHAR(16) NOT NULL DEFAULT 'CREADO',
        transporte VARCHAR(16) NOT NULL DEFAULT 'local',
        error VARCHAR(255) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        aplicado_en DATETIME DEFAULT NULL,
        UNIQUE KEY uq_paq (id_empresa, uuid),
        INDEX idx_paq_estado (id_empresa, estado, creado),
        INDEX idx_paq_dest (id_empresa, destino_tienda, estado)"""),

    ("terminal_versiones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        version_sw VARCHAR(20) DEFAULT NULL,
        version_db VARCHAR(10) DEFAULT NULL,
        ultima_sync DATETIME DEFAULT NULL,
        ultimo_paquete CHAR(36) DEFAULT NULL,
        revision INT NOT NULL DEFAULT 0,
        hash VARCHAR(64) DEFAULT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_termver (id_empresa, id_tienda)"""),

    ("sync_sesiones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        uuid CHAR(36) NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        origen_tienda INT NOT NULL DEFAULT 0,
        destino_tienda INT NOT NULL DEFAULT 0,
        transporte VARCHAR(16) NOT NULL DEFAULT 'local',
        inicio DATETIME DEFAULT CURRENT_TIMESTAMP,
        fin DATETIME DEFAULT NULL,
        duracion_ms INT DEFAULT NULL,
        bytes INT NOT NULL DEFAULT 0,
        num_eventos INT NOT NULL DEFAULT 0,
        num_paquetes INT NOT NULL DEFAULT 0,
        estado VARCHAR(16) NOT NULL DEFAULT 'EN_CURSO',
        error VARCHAR(255) DEFAULT NULL,
        INDEX idx_ses (id_empresa, inicio),
        INDEX idx_ses_dest (id_empresa, destino_tienda, estado)"""),

    ("sync_actualizaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        version VARCHAR(20) NOT NULL,
        canal VARCHAR(12) NOT NULL DEFAULT 'normal',
        critico TINYINT(1) NOT NULL DEFAULT 0,
        descripcion VARCHAR(255) DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        firma VARCHAR(255) DEFAULT NULL,
        url VARCHAR(255) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'DISPONIBLE',
        publicado DATETIME DEFAULT CURRENT_TIMESTAMP,
        aplicado_en DATETIME DEFAULT NULL,
        INDEX idx_upd (id_empresa, estado, publicado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
