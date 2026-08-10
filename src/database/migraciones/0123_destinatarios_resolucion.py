"""
Migración 0123 — Servicio Corporativo de Resolución de Destinatarios. ADITIVA, idempotente, reversible.

NO duplica agendas ni entidades: los datos (clientes, proveedores, empleados…) siguen viviendo en sus
módulos. Solo añade el soporte propio del servicio de resolución que HOY no existe:

  · `destinatarios_historico`  — aprendizaje: todo destinatario ya usado (aunque no pertenezca al ERP)
    con nº de envíos, último envío, módulo/contexto, empresa y usuario. Base de "recientes" y del
    orden por frecuencia (Partes D/J/Q).
  · `destinatarios_favoritos`  — favoritos por usuario y empresa (Parte I).

Todo multiempresa (id_empresa en cada fila y en las claves UNIQUE). Preparado para SaaS multitenant.
"""

VERSION = "0123"
DESCRIPCION = "Resolución de destinatarios: histórico de aprendizaje + favoritos (multiempresa)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("destinatarios_historico", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_usuario VARCHAR(80) DEFAULT NULL,
        correo VARCHAR(255) NOT NULL,
        nombre_mostrado VARCHAR(200) DEFAULT NULL,
        modulo_contexto VARCHAR(40) DEFAULT NULL,
        num_envios INT NOT NULL DEFAULT 1,
        ultimo_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_hist_dest (id_empresa, id_usuario, correo),
        INDEX idx_hist_emp (id_empresa, ultimo_envio),
        INDEX idx_hist_correo (id_empresa, correo)"""),
    ("destinatarios_favoritos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        id_usuario VARCHAR(80) DEFAULT NULL,
        correo VARCHAR(255) NOT NULL,
        nombre_mostrado VARCHAR(200) DEFAULT NULL,
        tipo VARCHAR(40) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_fav_dest (id_empresa, id_usuario, correo),
        INDEX idx_fav_emp (id_empresa, id_usuario)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
