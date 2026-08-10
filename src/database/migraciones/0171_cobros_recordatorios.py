"""
Migración 0171 — Recordatorios de cobro (dunning de clientes). ADITIVA e IDEMPOTENTE.

Tabla `cobros_recordatorios`: registra cada recordatorio de cobro ENVIADO por factura y nivel de escalado,
para no duplicar envíos (idempotencia por factura+nivel) y auditar. No modifica datos existentes.
"""

VERSION = "0171"
DESCRIPCION = "Recordatorios de cobro: tabla cobros_recordatorios"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cobros_recordatorios (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  DEFAULT NULL,
            id_factura  INT          NOT NULL,
            nivel       INT          NOT NULL DEFAULT 0,
            etiqueta    VARCHAR(80)           DEFAULT NULL,
            canal       VARCHAR(20)           DEFAULT NULL,
            destino     VARCHAR(255)          DEFAULT NULL,
            estado      VARCHAR(20)  NOT NULL DEFAULT 'enviado',
            fecha       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cobros_rec (id_empresa, id_factura)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cobros_recordatorios")
