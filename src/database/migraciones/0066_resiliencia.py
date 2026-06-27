"""
Migracion 0066 — Resiliencia / Continuidad operativa (Bloque 7). ADITIVA, idempotente, reversible.

Tablas SERVIDOR del patron outbox/inbox + event sourcing operativo + circuit breakers + watchdog +
edge nodes + chaos. NO toca fiscal_cola/contab_cola/kardex/auditoria existentes (los reutiliza como
referencia). El almacen OFFLINE de tienda es SQLite local (no MariaDB) — ver offline_store.py.
Multiempresa/multitienda.
"""

VERSION = "0066"
DESCRIPCION = "Resiliencia: sync_outbox/inbox/conflictos/reintentos, operational_events, circuit_breakers, edge_nodes, chaos"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── B7-C · Outbox / Inbox ─────────────────────────────────────────────────
    ("sync_outbox", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        entidad VARCHAR(40) NOT NULL,
        operacion VARCHAR(16) NOT NULL DEFAULT 'upsert',
        payload MEDIUMTEXT DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        idempotency_key VARCHAR(80) NOT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        intentos INT NOT NULL DEFAULT 0,
        proximo_intento DATETIME DEFAULT NULL,
        error VARCHAR(255) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        confirmado_en DATETIME DEFAULT NULL,
        UNIQUE KEY uq_outbox (idempotency_key),
        INDEX idx_outbox (id_empresa, estado, proximo_intento)"""),
    ("sync_inbox", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        entidad VARCHAR(40) NOT NULL,
        idempotency_key VARCHAR(80) NOT NULL,
        payload MEDIUMTEXT DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'recibido',
        procesado_en DATETIME DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_inbox (idempotency_key),
        INDEX idx_inbox (id_empresa, estado)"""),
    ("sync_conflictos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        entidad VARCHAR(40) NOT NULL,
        idempotency_key VARCHAR(80) DEFAULT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        payload_local MEDIUMTEXT DEFAULT NULL,
        payload_central MEDIUMTEXT DEFAULT NULL,
        resolucion VARCHAR(16) DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'abierto',
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        resuelto_en DATETIME DEFAULT NULL,
        INDEX idx_conflicto (id_empresa, estado)"""),
    ("sync_reintentos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_outbox BIGINT NOT NULL,
        intento INT NOT NULL,
        resultado VARCHAR(12) NOT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_reint (id_outbox)"""),
    # ── B7-E · Event sourcing operativo ───────────────────────────────────────
    ("operational_events", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        tipo VARCHAR(40) NOT NULL,
        agregado VARCHAR(40) NOT NULL,
        agregado_id VARCHAR(64) DEFAULT NULL,
        payload MEDIUMTEXT DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        hash_anterior VARCHAR(64) DEFAULT NULL,
        secuencia BIGINT NOT NULL DEFAULT 0,
        origen VARCHAR(12) NOT NULL DEFAULT 'central',
        idempotency_key VARCHAR(80) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_oevent (id_empresa, idempotency_key),
        INDEX idx_oevent (id_empresa, agregado, agregado_id, secuencia)"""),
    ("event_snapshots", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        agregado VARCHAR(40) NOT NULL,
        agregado_id VARCHAR(64) DEFAULT NULL,
        secuencia BIGINT NOT NULL DEFAULT 0,
        estado MEDIUMTEXT DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_snap (id_empresa, agregado, agregado_id, secuencia)"""),
    ("event_replay_log", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        agregado VARCHAR(40) DEFAULT NULL,
        agregado_id VARCHAR(64) DEFAULT NULL,
        eventos INT NOT NULL DEFAULT 0,
        desde_secuencia BIGINT NOT NULL DEFAULT 0,
        hasta_secuencia BIGINT NOT NULL DEFAULT 0,
        resultado VARCHAR(12) NOT NULL DEFAULT 'ok',
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_replay (id_empresa, agregado)"""),
    # ── B7-F · Circuit breakers (estado persistente) ──────────────────────────
    ("circuit_breakers", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        servicio VARCHAR(40) NOT NULL,
        estado VARCHAR(10) NOT NULL DEFAULT 'closed',
        fallos INT NOT NULL DEFAULT 0,
        max_fallos INT NOT NULL DEFAULT 5,
        ventana_seg INT NOT NULL DEFAULT 60,
        cooldown_seg INT NOT NULL DEFAULT 30,
        abierto_desde DATETIME DEFAULT NULL,
        ultimo_fallo DATETIME DEFAULT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_breaker (servicio, id_empresa)"""),
    # ── B7-H · Edge nodes (estado de tienda) ──────────────────────────────────
    ("edge_nodes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        nombre VARCHAR(120) DEFAULT NULL,
        modo VARCHAR(12) NOT NULL DEFAULT 'online',
        ultima_sincronizacion DATETIME DEFAULT NULL,
        eventos_pendientes INT NOT NULL DEFAULT 0,
        salud VARCHAR(12) NOT NULL DEFAULT 'ok',
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_edge (id_empresa, id_tienda)"""),
    # ── B7-J · Chaos / simulacros de desastre ─────────────────────────────────
    ("chaos_ejecuciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        escenario VARCHAR(40) NOT NULL,
        resultado VARCHAR(12) NOT NULL DEFAULT 'ok',
        tiempo_recuperacion_seg DECIMAL(10,2) NOT NULL DEFAULT 0,
        acciones VARCHAR(255) DEFAULT NULL,
        detalle TEXT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_chaos (escenario, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
