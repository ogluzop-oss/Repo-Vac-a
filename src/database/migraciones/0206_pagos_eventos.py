"""
Migración 0206 — Ledger inmutable de pagos + soporte de conciliación. ADITIVA, idempotente, reversible.

Marketplace + Pagos (F4):
- `pagos_eventos`: registro APPEND-ONLY (event sourcing) de cada movimiento de fondos de una transacción de
  la Lonja (retención/liberación/disputa/reembolso). Trazabilidad inmutable (la fuente de verdad de los
  movimientos); el asiento contable de la COMISIÓN de la plataforma se cruza aparte (idempotente).
- `lonja_transacciones.iban_virtual_ref`: referencia del IBAN virtual asignado a la operación, para conciliar
  automáticamente una transferencia entrante.
- `lonja_transacciones.asiento_comision`: id del asiento contable de la comisión (traza + idempotencia).
"""

VERSION = "0206"
DESCRIPCION = "Ledger inmutable de pagos (pagos_eventos) + iban_virtual_ref/asiento_comision en Lonja"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS_TX = (
    ("iban_virtual_ref", "VARCHAR(64) DEFAULT NULL"),
    ("asiento_comision", "BIGINT DEFAULT NULL"),
)

_TABLAS = [
    ("pagos_eventos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_transaccion BIGINT NOT NULL,
        tipo VARCHAR(32) NOT NULL,
        importe DECIMAL(14,4) NOT NULL DEFAULT 0,
        comision DECIMAL(14,4) NOT NULL DEFAULT 0,
        divisa VARCHAR(8) NOT NULL DEFAULT 'EUR',
        payment_ref VARCHAR(120) DEFAULT NULL,
        transfer_ref VARCHAR(120) DEFAULT NULL,
        payload TEXT DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_pev_tx (id_transaccion),
        INDEX idx_pev_emp (id_empresa, creado_en)"""),
]


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for col, ddl in _COLS_TX:
        if not _tiene_columna(cur, "lonja_transacciones", col):
            cur.execute(f"ALTER TABLE lonja_transacciones ADD COLUMN {col} {ddl}")


def revertir(cur):
    for col, _ in reversed(_COLS_TX):
        if _tiene_columna(cur, "lonja_transacciones", col):
            cur.execute(f"ALTER TABLE lonja_transacciones DROP COLUMN {col}")
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
