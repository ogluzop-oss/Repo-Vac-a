"""
Migración 0125 — CCP Fase II · B1 Corporate Templates Manager. ADITIVA, idempotente, reversible.

Evoluciona las plantillas a un gestor documental corporativo con versionado, categorías, idiomas y
estados (borrador/producción/archivada). NO sustituye `plantillas_correo`: lo complementa (el render
sigue reutilizando el sistema existente). Multiempresa.
"""

VERSION = "0125"
DESCRIPCION = "CCP II · Templates Manager: ccp_plantillas + versiones (categorías/idiomas/estados)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ccp_plantillas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        codigo VARCHAR(80) NOT NULL,
        categoria VARCHAR(40) DEFAULT 'general',
        idioma VARCHAR(8) DEFAULT 'es',
        formato VARCHAR(12) NOT NULL DEFAULT 'texto',
        estado VARCHAR(16) NOT NULL DEFAULT 'borrador',
        asunto VARCHAR(255) DEFAULT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        condiciones TEXT DEFAULT NULL,
        version_actual INT NOT NULL DEFAULT 1,
        autor VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        UNIQUE KEY uq_ccp_pl (id_empresa, codigo, idioma),
        INDEX idx_ccp_pl (id_empresa, categoria, estado)"""),
    ("ccp_plantillas_versiones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_plantilla BIGINT NOT NULL,
        id_empresa CHAR(36) DEFAULT NULL,
        version INT NOT NULL DEFAULT 1,
        formato VARCHAR(12) NOT NULL DEFAULT 'texto',
        estado VARCHAR(16) NOT NULL DEFAULT 'borrador',
        asunto VARCHAR(255) DEFAULT NULL,
        cuerpo MEDIUMTEXT DEFAULT NULL,
        autor VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ccp_plv (id_plantilla, version),
        INDEX idx_ccp_plv (id_plantilla)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
