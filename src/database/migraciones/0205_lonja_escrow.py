"""
Migración 0205 — Estado de pago (escrow) en las transacciones de la Lonja. ADITIVA, idempotente, reversible.

Marketplace + Pagos (F2). Añade a `lonja_transacciones` el estado del flujo de fondos custodiados (escrow)
del PSP, además de las referencias del PSP y la comisión de la plataforma. Columnas NULLABLE / con DEFAULT:
las transacciones existentes quedan con `estado_pago = NULL` (no usan escrow), 100% compatibles hacia atrás.

Estados de pago: PAYMENT_PENDING → FUNDS_HELD → IN_FULFILLMENT → DELIVERY_CONFIRMED → FUNDS_RELEASED, con
ramas IN_DISPUTE y REFUNDED. La transición y los importes los ejecuta el motor F1 (`PasarelaMarketplace`);
esta tabla solo REGISTRA el estado (la custodia de fondos vive en el PSP, no en Smart Manager).
"""

VERSION = "0205"
DESCRIPCION = "Escrow en lonja_transacciones (estado_pago + refs PSP + comisión de plataforma)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = (
    ("estado_pago", "VARCHAR(24) DEFAULT NULL"),
    ("psp_payment_ref", "VARCHAR(120) DEFAULT NULL"),
    ("psp_transfer_ref", "VARCHAR(120) DEFAULT NULL"),
    ("comision_importe", "DECIMAL(14,4) NOT NULL DEFAULT 0"),
    ("idem_key_pago", "VARCHAR(80) DEFAULT NULL"),
    ("held_en", "DATETIME DEFAULT NULL"),
    ("released_en", "DATETIME DEFAULT NULL"),
)


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _COLS:
        if not _tiene_columna(cur, "lonja_transacciones", col):
            cur.execute(f"ALTER TABLE lonja_transacciones ADD COLUMN {col} {ddl}")


def revertir(cur):
    for col, _ in reversed(_COLS):
        if _tiene_columna(cur, "lonja_transacciones", col):
            cur.execute(f"ALTER TABLE lonja_transacciones DROP COLUMN {col}")
