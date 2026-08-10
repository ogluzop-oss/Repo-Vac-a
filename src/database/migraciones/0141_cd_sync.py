"""
Migración 0141 — PCD · Fase 6 (RFC-CD-002/005): Sync Engine (Outbox + Inbox de deduplicación).

Realiza la persistencia del motor de sincronización autorizado en el alcance de la Fase 6 (Outbox +
Idempotencia + Deduplicación). NO contiene lógica de proveedor. El transporte real, el Event Bus, el
Scheduler y la Observabilidad se REUTILIZAN vía capacidades (no se recrean).

  · cd_sync_outbox — mensajes salientes (Dominio → Adaptador → Canal). Idempotencia por
    (empresa, canal, idempotencia_key). Reintentos con backoff.
  · cd_sync_inbox  — deduplicación de mensajes entrantes por (empresa, canal, external_id).

ADITIVA, idempotente, reversible (tablas nuevas → revert las elimina). No elimina ni altera datos.
"""

VERSION = "0141"
DESCRIPCION = "PCD Fase 6: Sync Engine (cd_sync_outbox + cd_sync_inbox)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_sync_outbox", """
        id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa       CHAR(36)              DEFAULT NULL,
        canal            VARCHAR(40)  NOT NULL,
        tipo             VARCHAR(60)  NOT NULL,                 -- tipo de mensaje neutro (dominio)
        direccion        VARCHAR(10)  NOT NULL DEFAULT 'push',
        idempotencia_key VARCHAR(160)          DEFAULT NULL,
        correlation_id   VARCHAR(80)           DEFAULT NULL,
        communication_id VARCHAR(80)           DEFAULT NULL,    -- CCP cuando proceda
        payload          MEDIUMTEXT,                            -- payload neutro (JSON)
        estado           VARCHAR(16)  NOT NULL DEFAULT 'PENDIENTE', -- PENDIENTE|ENVIADO|ERROR|DESCARTADO
        intentos         INT          NOT NULL DEFAULT 0,
        max_intentos     INT          NOT NULL DEFAULT 5,
        proximo_intento  DATETIME              DEFAULT NULL,
        ultimo_error     VARCHAR(255)          DEFAULT NULL,
        ts_creado        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_actualizado   DATETIME              DEFAULT NULL,
        UNIQUE KEY uq_outbox_idem (id_empresa, canal, idempotencia_key),
        INDEX idx_outbox_estado (estado, proximo_intento),
        INDEX idx_outbox_canal (id_empresa, canal)"""),
    ("cd_sync_inbox", """
        id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa     CHAR(36)              DEFAULT NULL,
        canal          VARCHAR(40)  NOT NULL,
        external_id    VARCHAR(180) NOT NULL,                   -- id del sistema externo (dedup)
        tipo           VARCHAR(60)           DEFAULT NULL,
        correlation_id VARCHAR(80)           DEFAULT NULL,
        payload        MEDIUMTEXT,
        estado         VARCHAR(16)  NOT NULL DEFAULT 'RECIBIDO', -- RECIBIDO|PROCESADO|DESCARTADO
        ts_creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_inbox_ext (id_empresa, canal, external_id),
        INDEX idx_inbox_estado (estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
