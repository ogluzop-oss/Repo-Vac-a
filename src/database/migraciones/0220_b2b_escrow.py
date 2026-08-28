"""
Migración 0220 — Smart Suppliers · Fase A: custodia de fondos (escrow) para pedidos B2B. ADITIVA,
idempotente, reversible.

`b2b_escrow` es 1:1 con una fila de `transaccion_comercial` (motor de Comercio Digital vigente, ver
migración 0139) — NO se crea un motor de transacciones paralelo, solo el seguimiento de la custodia de
fondos de ESA transacción, delegando la operación real en `PasarelaMarketplace`
(`src/services/tpv/pagos/base_marketplace.py`, ya existente).

`b2b_escrow_ledger` es un libro contable INMUTABLE (append-only, sin UPDATE/DELETE en el código de
aplicación) encadenado por hash: cada fila incluye el hash de la fila anterior, de modo que alterar un
movimiento histórico rompe la cadena y es detectable.
"""

VERSION = "0220"
DESCRIPCION = "Smart Suppliers: custodia de fondos (escrow) 1:1 sobre transaccion_comercial + ledger inmutable"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("b2b_escrow", """
        id_tx CHAR(36) NOT NULL PRIMARY KEY,
        estado_pago VARCHAR(30) NOT NULL DEFAULT 'PAYMENT_PENDING',
        psp_payment_ref VARCHAR(160) DEFAULT NULL,
        psp_transfer_ref VARCHAR(160) DEFAULT NULL,
        importe_retenido DECIMAL(12,2) NOT NULL DEFAULT 0,
        comision DECIMAL(12,2) NOT NULL DEFAULT 0,
        divisa VARCHAR(3) NOT NULL DEFAULT 'EUR',
        retenido_en DATETIME DEFAULT NULL,
        liberado_en DATETIME DEFAULT NULL,
        motivo_liberacion VARCHAR(30) DEFAULT NULL,
        creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_escrow_estado (estado_pago)"""),
    ("b2b_escrow_ledger", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_tx CHAR(36) NOT NULL,
        tipo VARCHAR(20) NOT NULL,
        monto DECIMAL(12,2) NOT NULL DEFAULT 0,
        actor VARCHAR(120) DEFAULT NULL,
        ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        hash_previo CHAR(64) DEFAULT NULL,
        hash_actual CHAR(64) NOT NULL,
        referencia_psp VARCHAR(160) DEFAULT NULL,
        INDEX idx_ledger_tx (id_tx)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
