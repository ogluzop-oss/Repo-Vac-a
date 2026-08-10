"""
Migración 0124 — Corporate Communication Platform (CCP): registro unificado de comunicaciones.
ADITIVA, idempotente, reversible.

Da soporte al **Communication ID** (`COM-AAAA-NNNNNNNN`), independiente del canal, que unifica la
auditoría/historial/telemetría de TODA comunicación corporativa (correo hoy; WhatsApp/SMS/… mañana).
No duplica el historial de correos existente: registra la comunicación a nivel de plataforma con su
estado por canal. Multiempresa (id_empresa por fila).
"""

VERSION = "0124"
DESCRIPCION = "CCP: registro unificado de comunicaciones (Communication ID + estado por canal)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ccp_comunicaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        com_id VARCHAR(24) DEFAULT NULL,
        id_empresa CHAR(36) DEFAULT NULL,
        canal VARCHAR(30) NOT NULL DEFAULT 'email',
        estado VARCHAR(20) NOT NULL DEFAULT 'preparada',
        destinatario VARCHAR(255) DEFAULT NULL,
        asunto VARCHAR(255) DEFAULT NULL,
        contexto VARCHAR(40) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        UNIQUE KEY uq_ccp_comid (com_id),
        INDEX idx_ccp_emp (id_empresa, creado),
        INDEX idx_ccp_canal (id_empresa, canal, estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
