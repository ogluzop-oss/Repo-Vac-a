"""
Migracion 0106 — Enriquecimiento de Logística (Módulo 6). ADITIVA, idempotente, reversible.
Auditoría: incidencias logísticas, recepciones y documentos/albaranes ya existen. Se añade lo ausente:
transportistas y expediciones (con seguimiento/tracking, coste, entrega programada/parcial). Reutiliza
pedidos/picking existentes como origen. No duplica.
"""

VERSION = "0106"
DESCRIPCION = "Logística: transportistas + expediciones (tracking/coste/entregas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("logistica_transportistas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        nombre VARCHAR(120) NOT NULL,
        contacto VARCHAR(120) DEFAULT NULL,
        telefono VARCHAR(40) DEFAULT NULL,
        url_seguimiento VARCHAR(255) DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_transp (id_empresa, activo)"""),
    ("logistica_expediciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        referencia VARCHAR(80) DEFAULT NULL,
        id_transportista INT DEFAULT NULL,
        origen VARCHAR(40) DEFAULT 'pedido',
        id_documento VARCHAR(64) DEFAULT NULL,
        direccion VARCHAR(255) DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'PREPARACION',
        tracking VARCHAR(120) DEFAULT NULL,
        coste DECIMAL(12,2) DEFAULT 0,
        parcial TINYINT NOT NULL DEFAULT 0,
        fecha_programada DATE DEFAULT NULL,
        fecha_envio DATETIME DEFAULT NULL,
        fecha_entrega DATETIME DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_exped (id_empresa, estado, fecha_programada)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
