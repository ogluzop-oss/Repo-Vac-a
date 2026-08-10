"""
Migración 0147 — PCD · Etapa B · Fase B6: ledger de pagos (cd_pagos).

Registro de intentos/estados de pago por Transacción Comercial. La PASARELA se REUTILIZA
(services.tpv.pagos: stripe/paypal/redsys/simulado, provider-agnostic); aquí solo se traza el pago y
se deduplican los webhooks. Las credenciales viven en `cd_conexiones` (cifradas), nunca aquí.

ADITIVA, idempotente, reversible. Multiempresa. No elimina ni altera datos.
"""

VERSION = "0147"
DESCRIPCION = "PCD Etapa B/F6: cd_pagos (ledger de pagos + dedup de webhooks)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_pagos", """
        id                 BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa         CHAR(36)              DEFAULT NULL,
        id_tx              CHAR(36)     NOT NULL,
        proveedor          VARCHAR(40)           DEFAULT NULL,   -- stripe|paypal|redsys|simulado|…
        referencia_externa VARCHAR(160)          DEFAULT NULL,   -- ref del cobro en la pasarela
        importe            DECIMAL(12,4) NOT NULL DEFAULT 0,
        moneda             VARCHAR(8)   NOT NULL DEFAULT 'EUR',
        estado             VARCHAR(16)  NOT NULL DEFAULT 'iniciado', -- iniciado|pagado|fallido|reembolsado
        url_pago           VARCHAR(255)          DEFAULT NULL,
        webhook_event_id   VARCHAR(160)          DEFAULT NULL,   -- dedup de webhooks
        actor              VARCHAR(120)          DEFAULT NULL,
        ts_creado          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_actualizado     DATETIME              DEFAULT NULL,
        INDEX idx_pagos_tx (id_empresa, id_tx),
        INDEX idx_pagos_estado (id_empresa, estado),
        UNIQUE KEY uq_pago_webhook (id_empresa, proveedor, webhook_event_id)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
