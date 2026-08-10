"""
Migración 0140 — PCD · Fase 5 (RFC-CD-005): Reservation Ledger (cd_reservas).

LIBRO CONTABLE append-only (como el Kárdex): nunca se edita/sobrescribe una reserva; cada cambio de
estado registra una FILA nueva (SOFT_CREATED → HARD_CONFIRMED → RELEASED/CONSUMED/EXPIRED). Toda
reserva pertenece SIEMPRE a una Transacción (id_tx) y a una Línea (id_linea) — sin huérfanas. Es el
ÚNICO mecanismo que reduce el ATP. OMNICANAL (mismo ledger para todos los canales). Multiempresa.
ADITIVA, idempotente, reversible (tabla nueva → revert la elimina).
"""

VERSION = "0140"
DESCRIPCION = "PCD Fase 5: Reservation Ledger append-only (cd_reservas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_reservas", """
        id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_reserva   CHAR(36)     NOT NULL,                 -- agrupa los apuntes de una reserva
        id_empresa   CHAR(36)     DEFAULT NULL,
        id_tx        CHAR(36)     NOT NULL,                 -- pertenece SIEMPRE a una transacción
        id_linea     BIGINT                DEFAULT NULL,    -- y a una línea (aclaración 3)
        codigo_articulo VARCHAR(50)        DEFAULT NULL,
        bucket       VARCHAR(30)           DEFAULT NULL,    -- origen (tienda_activa/central/...)
        cantidad     INT          NOT NULL DEFAULT 0,
        tipo         VARCHAR(10)  NOT NULL DEFAULT 'soft',  -- soft|hard
        estado       VARCHAR(16)  NOT NULL,                 -- SOFT_CREATED|HARD_CONFIRMED|RELEASED|CONSUMED|EXPIRED
        canal        VARCHAR(30)           DEFAULT NULL,    -- informativo (omnicanal: mismo ledger)
        ttl_expira   DATETIME              DEFAULT NULL,
        actor        VARCHAR(120)          DEFAULT NULL,
        ts           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_cdr_reserva (id_reserva),
        INDEX idx_cdr_atp (id_empresa, codigo_articulo, estado),
        INDEX idx_cdr_tx (id_tx),
        INDEX idx_cdr_exp (estado, ttl_expira)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
