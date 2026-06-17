"""
Migración 0006 — Auditoría del ciclo de vida de certificados (C3.5.4). ADITIVA.

Rastro inmutable de eventos (importar/activar/revocar/rotar) por empresa, para
trazabilidad SaaS y cumplimiento. No contiene material criptográfico (solo metadatos
del evento). Multiempresa por `id_empresa`. Idempotente, reversible.
"""

VERSION = "0006"
DESCRIPCION = "Auditoría de certificados (fiscal_certificados_auditoria)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fiscal_certificados_auditoria (
            id            BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa    CHAR(36)    NOT NULL,
            id_certificado BIGINT              DEFAULT NULL,
            accion        VARCHAR(20) NOT NULL,                 -- importar|activar|revocar|rotar
            detalle       VARCHAR(255)         DEFAULT NULL,
            id_usuario    INT                  DEFAULT NULL,
            usuario       VARCHAR(120)         DEFAULT NULL,
            fecha         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_certaud_emp (id_empresa),
            INDEX idx_certaud_cert (id_certificado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS fiscal_certificados_auditoria")
