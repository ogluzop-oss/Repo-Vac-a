"""
Migracion 0119 — Enriquecimiento de Documentación (Módulo 19). ADITIVA, idempotente, reversible.
Auditoría: existe un CENTRO DOCUMENTAL unificado (`documentos_registro`: tipo, nombre, referencia,
ruta, hash_documental, estado, fecha) con visor. Se añade lo ausente: VERSIONADO de documentos,
RETENCIÓN/caducidad documental (con archivado/purga vía Scheduler) y ETIQUETAS/clasificación. No
reescribe `documentos_registro`: lo referencia por `id_documento`. No duplica.
"""

VERSION = "0119"
DESCRIPCION = "Documentación: versionado + retención/caducidad + etiquetas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("documento_versiones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_documento INT NOT NULL,
        version INT NOT NULL DEFAULT 1,
        ruta VARCHAR(255) DEFAULT NULL,
        hash_documental VARCHAR(128) DEFAULT NULL,
        nota VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_docver (id_documento, version)"""),
    ("documento_retencion", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_documento INT NOT NULL,
        politica VARCHAR(60) DEFAULT NULL,
        fecha_caducidad DATE DEFAULT NULL,
        archivado TINYINT NOT NULL DEFAULT 0,
        purgado TINYINT NOT NULL DEFAULT 0,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_retencion (id_documento)"""),
    ("documento_etiquetas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_documento INT NOT NULL,
        etiqueta VARCHAR(60) NOT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_etiqueta (id_documento, etiqueta),
        INDEX idx_etiqueta (id_empresa, etiqueta)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
