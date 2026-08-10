"""
Migracion 0087 — Motor Corporativo de Eventos (Fase 1). ADITIVA, idempotente, reversible.

Crea el nucleo de persistencia del Event Bus interno: catalogo de tipos, eventos, sus
destinatarios, transiciones de estado, historial de ciclo de vida y log tecnico. NO toca
ninguna tabla existente (Verifactu, facturacion, kardex, contab_cola, operational_events,
sync_outbox/inbox, notificaciones... se conservan intactas). Multiempresa/multitienda/SaaS.

Caracter OBSERVACIONAL: en la Fase 1 los eventos se PUBLICAN y persisten, pero ningun
modulo los consume todavia. Preparado para millones de eventos (indices por empresa/tipo/
estado/fecha) y para versionado sin romper compatibilidad.
"""

VERSION = "0087"
DESCRIPCION = "Motor de eventos: eventos_tipo, eventos, eventos_destinatarios, eventos_estado, eventos_historial, eventos_log"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── Catalogo de tipos de evento (global; ampliable a miles de tipos) ────────
    ("eventos_tipo", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(60) NOT NULL,
        categoria VARCHAR(40) DEFAULT NULL,
        descripcion VARCHAR(180) DEFAULT NULL,
        prioridad_defecto VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        activo TINYINT(1) NOT NULL DEFAULT 1,
        schema_version INT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_evttipo (codigo),
        INDEX idx_evttipo_cat (categoria, activo)"""),

    # ── Eventos (nucleo) ────────────────────────────────────────────────────────
    ("eventos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        uuid CHAR(36) NOT NULL,
        tipo VARCHAR(60) NOT NULL,
        prioridad VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        estado VARCHAR(16) NOT NULL DEFAULT 'CREADO',
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        id_almacen INT DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        origen VARCHAR(60) DEFAULT NULL,
        destino VARCHAR(60) DEFAULT NULL,
        version INT NOT NULL DEFAULT 1,
        schema_version INT NOT NULL DEFAULT 1,
        created_with VARCHAR(24) DEFAULT NULL,
        updated_with VARCHAR(24) DEFAULT NULL,
        ref_entidad VARCHAR(60) DEFAULT NULL,
        ref_id VARCHAR(80) DEFAULT NULL,
        payload MEDIUMTEXT DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        observaciones VARCHAR(255) DEFAULT NULL,
        reintentos INT NOT NULL DEFAULT 0,
        procesado_ms INT DEFAULT NULL,
        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_evento (id_empresa, uuid),
        INDEX idx_evt_tipo (id_empresa, tipo, estado, fecha_creacion),
        INDEX idx_evt_tienda (id_empresa, id_tienda, fecha_creacion),
        INDEX idx_evt_estado (id_empresa, estado, prioridad),
        INDEX idx_evt_ref (id_empresa, ref_entidad, ref_id)"""),

    # ── Destinatarios de cada evento (para consumo/distribucion futura) ─────────
    ("eventos_destinatarios", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_evento BIGINT NOT NULL,
        destino VARCHAR(80) NOT NULL,
        tipo_destino VARCHAR(12) NOT NULL DEFAULT 'modulo',
        estado VARCHAR(16) NOT NULL DEFAULT 'PENDIENTE',
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_evtdest (id_empresa, id_evento),
        INDEX idx_evtdest_estado (id_empresa, destino, estado)"""),

    # ── Transiciones de estado (maquina de estados del evento) ──────────────────
    ("eventos_estado", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_evento BIGINT NOT NULL,
        estado_anterior VARCHAR(16) DEFAULT NULL,
        estado_nuevo VARCHAR(16) NOT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_evtestado (id_empresa, id_evento, fecha)"""),

    # ── Historial de ciclo de vida (quien creo/consumio/fallo, tiempos) ─────────
    ("eventos_historial", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_evento BIGINT NOT NULL,
        accion VARCHAR(24) NOT NULL,
        actor VARCHAR(80) DEFAULT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        duracion_ms INT DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_evthist (id_empresa, id_evento, fecha)"""),

    # ── Log tecnico del bus (diagnostico/metricas; nunca datos sensibles) ───────
    ("eventos_log", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_evento BIGINT DEFAULT NULL,
        nivel VARCHAR(10) NOT NULL DEFAULT 'INFO',
        origen VARCHAR(60) DEFAULT NULL,
        mensaje VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_evtlog (id_empresa, fecha)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    # Siembra (idempotente) el catalogo semilla de tipos de evento. Best-effort: si fallara,
    # la creacion de tablas ya quedo garantizada y el catalogo se resiembra en el proximo arranque.
    try:
        from src.services.eventos import tipos as _T
        _T.sembrar(cur)
    except Exception:
        pass


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
