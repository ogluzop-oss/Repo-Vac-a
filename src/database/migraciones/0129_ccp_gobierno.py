"""
Migración 0129 — CCP Fase II · B10 Communication Governance. ADITIVA, idempotente, reversible.

Gobierno de comunicaciones: consentimientos (RGPD) y políticas (listas negras/blancas, canales
permitidos/prohibidos, retención…). Se aplican en el pipeline del Communication Service y quedan
asociadas al Communication ID. Multiempresa.
"""

VERSION = "0129"
DESCRIPCION = "CCP II · Governance: ccp_consentimientos + ccp_politicas_comunicacion (RGPD/políticas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ccp_consentimientos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        correo VARCHAR(255) NOT NULL,
        canal VARCHAR(30) NOT NULL DEFAULT 'email',
        estado VARCHAR(12) NOT NULL DEFAULT 'otorgado',
        base_legal VARCHAR(60) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ccp_cons (id_empresa, correo, canal),
        INDEX idx_ccp_cons (id_empresa, estado)"""),
    ("ccp_politicas_comunicacion", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        tipo VARCHAR(30) NOT NULL,
        valor VARCHAR(255) DEFAULT NULL,
        canal VARCHAR(30) DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        observaciones VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ccp_pol (id_empresa, tipo, activo)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
