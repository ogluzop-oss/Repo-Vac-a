"""
Migración 0126 — CCP Fase II · B3 Campaign Manager + Outgoing Queue. ADITIVA, idempotente, reversible.

Campañas corporativas + bandeja de salida real (BD) que despacha por el Corporate Communication
Service. Multiempresa.
"""

VERSION = "0126"
DESCRIPCION = "CCP II · Campañas + Outgoing Queue (ccp_campanas/destinatarios/cola)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ccp_campanas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        nombre VARCHAR(160) NOT NULL,
        tipo VARCHAR(30) DEFAULT 'aviso',
        canal VARCHAR(30) NOT NULL DEFAULT 'email',
        estado VARCHAR(16) NOT NULL DEFAULT 'borrador',
        plantilla_codigo VARCHAR(80) DEFAULT NULL,
        asunto VARCHAR(255) DEFAULT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        contexto VARCHAR(40) DEFAULT NULL,
        prioridad VARCHAR(12) DEFAULT 'normal',
        programada_para DATETIME DEFAULT NULL,
        total INT NOT NULL DEFAULT 0,
        enviados INT NOT NULL DEFAULT 0,
        fallidos INT NOT NULL DEFAULT 0,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_ccp_camp (id_empresa, estado)"""),
    ("ccp_campana_destinatarios", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_campana BIGINT NOT NULL,
        id_empresa CHAR(36) DEFAULT NULL,
        correo VARCHAR(255) NOT NULL,
        nombre VARCHAR(200) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'pendiente',
        com_id VARCHAR(24) DEFAULT NULL,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_ccp_campd (id_campana, estado)"""),
    ("ccp_cola", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        canal VARCHAR(30) NOT NULL DEFAULT 'email',
        destinatario VARCHAR(255) NOT NULL,
        asunto VARCHAR(255) DEFAULT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        plantilla_codigo VARCHAR(80) DEFAULT NULL,
        contexto VARCHAR(40) DEFAULT NULL,
        prioridad VARCHAR(12) DEFAULT 'normal',
        estado VARCHAR(16) NOT NULL DEFAULT 'pendiente',
        intentos INT NOT NULL DEFAULT 0,
        com_id VARCHAR(24) DEFAULT NULL,
        id_campana BIGINT DEFAULT NULL,
        programada_para DATETIME DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_ccp_cola (id_empresa, estado, prioridad),
        INDEX idx_ccp_cola_camp (id_campana)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
