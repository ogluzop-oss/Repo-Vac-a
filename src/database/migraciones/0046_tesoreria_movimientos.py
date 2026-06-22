"""
Migración 0046 — Movimientos de tesorería (rama Tesorería, FASE 2). ADITIVA, idempotente.

Libro financiero unificado `movimientos_tesoreria` con hash documental encadenado y
clave de idempotencia (id_empresa, origen, tipo, id_documento) — patrón M1. `importe` es
con signo (+ entrada / − salida); `saldo_resultante` es el saldo corrido de la cuenta.
"""

VERSION = "0046"
DESCRIPCION = "Libro de movimientos de tesorería (hash + idempotencia M1)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS movimientos_tesoreria (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa    VARCHAR(36)  NOT NULL,
            id_cuenta     INT          DEFAULT NULL,
            fecha         DATE         NOT NULL,
            tipo          VARCHAR(16)  NOT NULL,
            concepto      VARCHAR(255) DEFAULT NULL,
            importe       DECIMAL(14,2) NOT NULL DEFAULT 0,
            saldo_resultante DECIMAL(14,2) DEFAULT NULL,
            referencia    VARCHAR(80)  DEFAULT NULL,
            origen        VARCHAR(32)  NOT NULL DEFAULT 'manual',
            id_documento  VARCHAR(80)  DEFAULT NULL,
            usuario       VARCHAR(80)  DEFAULT NULL,
            hash          VARCHAR(64)  DEFAULT NULL,
            creado_en     DATETIME     DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_mt_cuenta (id_empresa, id_cuenta, fecha),
            INDEX idx_mt_fecha (id_empresa, fecha),
            INDEX idx_mt_origen (id_empresa, origen, tipo, id_documento)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Idempotencia M1: un (origen,tipo,id_documento) por empresa (NULL no colisiona en MySQL).
    cur.execute("ALTER TABLE movimientos_tesoreria ADD UNIQUE INDEX IF NOT EXISTS "
                "uq_mt_idem (id_empresa, origen, tipo, id_documento)")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS movimientos_tesoreria")
