"""
Migración 0128 — CCP Fase II · B7 Corporate Contacts CRM. ADITIVA, idempotente, reversible.

Relaciones entre entidades corporativas (jerarquías, responsables, sustitutos, pertenencia) NO
cubiertas hoy. No duplica entidades: solo registra RELACIONES entre las existentes. Multiempresa.
"""

VERSION = "0128"
DESCRIPCION = "CCP II · CRM: ccp_relaciones (jerarquías/responsables/relaciones entre entidades)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("ccp_relaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        origen_tipo VARCHAR(30) NOT NULL,
        origen_id VARCHAR(64) NOT NULL,
        destino_tipo VARCHAR(30) NOT NULL,
        destino_id VARCHAR(64) NOT NULL,
        rol VARCHAR(30) NOT NULL DEFAULT 'pertenece_a',
        observaciones VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ccp_rel (id_empresa, origen_tipo, origen_id, destino_tipo, destino_id, rol),
        INDEX idx_ccp_rel_o (id_empresa, origen_tipo, origen_id),
        INDEX idx_ccp_rel_d (id_empresa, destino_tipo, destino_id)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
