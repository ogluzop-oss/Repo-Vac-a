"""
Migración 0133 — Videovigilancia (Cámaras de Seguridad). ADITIVA, idempotente, reversible.

Cámaras por departamento (tienda/almacén/centro…) y registro de grabaciones diarias (24 h). AISLAMIENTO
ESTRICTO: cada fila lleva `id_empresa` + `id_centro`; ninguna consulta cruza departamentos ni empresas.
Las grabaciones son ficheros en disco (documentos/grabaciones/…) referenciados aquí y en Documentos.
"""

VERSION = "0133"
DESCRIPCION = "Videovigilancia: camaras + camaras_grabaciones (aislamiento empresa+centro)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("camaras", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_centro VARCHAR(64) DEFAULT NULL,
        tipo_centro VARCHAR(16) NOT NULL DEFAULT 'centro',
        nombre VARCHAR(120) NOT NULL,
        fuente VARCHAR(255) NOT NULL DEFAULT 'simulado',
        estado VARCHAR(16) NOT NULL DEFAULT 'activa',
        orden INT NOT NULL DEFAULT 0,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_cam (id_empresa, id_centro, estado)"""),
    ("camaras_grabaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_centro VARCHAR(64) DEFAULT NULL,
        id_camara BIGINT NOT NULL,
        fecha DATE NOT NULL,
        ruta VARCHAR(255) NOT NULL,
        duracion_seg INT NOT NULL DEFAULT 0,
        estado VARCHAR(16) NOT NULL DEFAULT 'grabando',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        UNIQUE KEY uq_grab (id_camara, fecha),
        INDEX idx_grab (id_empresa, id_centro, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
