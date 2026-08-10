"""
Migracion 0118 — Enriquecimiento de SAT/Helpdesk (Módulo 18). ADITIVA, idempotente, reversible.
Auditoría: SAT ya cubre tickets con SLA y colas, asignación/auto-asignación, comentarios, estados,
intervenciones, base de conocimiento, email-to-ticket, portal de cliente y analítica. Se añade lo
ausente: ENCUESTAS DE SATISFACCIÓN (CSAT/NPS) al cierre y BOLSA DE HORAS de contrato (consumo por
intervención). Reutiliza tickets/intervenciones/contratos existentes. No duplica.
"""

VERSION = "0118"
DESCRIPCION = "SAT: encuestas de satisfacción (CSAT) + bolsa de horas de contrato"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("sat_encuestas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_ticket INT NOT NULL,
        id_cliente INT DEFAULT NULL,
        token VARCHAR(48) DEFAULT NULL,
        puntuacion INT DEFAULT NULL,
        comentario VARCHAR(500) DEFAULT NULL,
        enviada TINYINT NOT NULL DEFAULT 0,
        respondida TINYINT NOT NULL DEFAULT 0,
        fecha_envio DATETIME DEFAULT NULL,
        fecha_respuesta DATETIME DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_encuesta (id_empresa, id_ticket)"""),
    ("sat_bolsas_horas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_contrato INT DEFAULT NULL,
        id_cliente INT DEFAULT NULL,
        descripcion VARCHAR(160) DEFAULT NULL,
        horas_totales DECIMAL(10,2) NOT NULL DEFAULT 0,
        horas_consumidas DECIMAL(10,2) NOT NULL DEFAULT 0,
        vigente TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_bolsa (id_empresa, id_cliente, vigente)"""),
    ("sat_consumo_horas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_bolsa INT NOT NULL,
        id_ticket INT DEFAULT NULL,
        horas DECIMAL(10,2) NOT NULL DEFAULT 0,
        concepto VARCHAR(200) DEFAULT NULL,
        fecha DATE DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_consumo (id_bolsa, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
