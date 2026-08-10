"""
Migracion 0088 — Motor Corporativo de Distribucion y Sincronizacion (Fase 2). ADITIVA,
idempotente, reversible. NO toca ninguna tabla existente (Verifactu, facturacion, kardex,
contabilidad, eventos*, edge_nodes, sync_outbox/inbox... se conservan intactas).

Crea la cola de distribucion, las confirmaciones (ACK) por terminal, la configuracion por
empresa (ventana de mantenimiento + politica de reintentos), el registro de conflictos y
una tabla LATERAL de versionado (`entidad_versiones`) que aporta version/revision/autor/
origen a cualquier entidad sincronizable SIN modificar sus tablas. El registro de terminales
se reutiliza de `edge_nodes` (Bloque 7). Multiempresa/multitienda/SaaS. Preparado para
millones de filas (indices por empresa/estado/fecha_programada).
"""

VERSION = "0088"
DESCRIPCION = "Distribucion: distribucion_pendiente, distribucion_confirmaciones, distribucion_config, distribucion_conflictos, entidad_versiones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    # ── Cola de distribucion (una fila por evento x destino) ────────────────────
    ("distribucion_pendiente", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        uuid CHAR(36) NOT NULL,
        id_evento BIGINT DEFAULT NULL,
        uuid_evento CHAR(36) DEFAULT NULL,
        tipo_evento VARCHAR(60) NOT NULL,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        destino VARCHAR(80) NOT NULL,
        tipo_destino VARCHAR(16) NOT NULL DEFAULT 'terminal',
        destino_tienda INT DEFAULT NULL,
        prioridad VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        sincronizacion VARCHAR(12) NOT NULL DEFAULT 'PROGRAMADA',
        estado VARCHAR(16) NOT NULL DEFAULT 'PENDIENTE',
        fecha_programada DATETIME DEFAULT NULL,
        fecha_envio DATETIME DEFAULT NULL,
        fecha_confirmacion DATETIME DEFAULT NULL,
        reintentos INT NOT NULL DEFAULT 0,
        proximo_intento DATETIME DEFAULT NULL,
        error VARCHAR(255) DEFAULT NULL,
        payload MEDIUMTEXT DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_distr (id_empresa, uuid),
        INDEX idx_distr_desp (id_empresa, estado, sincronizacion, fecha_programada),
        INDEX idx_distr_dest (id_empresa, destino, estado),
        INDEX idx_distr_evt (id_empresa, id_evento),
        INDEX idx_distr_reint (id_empresa, estado, proximo_intento)"""),

    # ── Confirmaciones (ACK) por terminal ───────────────────────────────────────
    ("distribucion_confirmaciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_distribucion BIGINT NOT NULL,
        id_evento BIGINT DEFAULT NULL,
        terminal VARCHAR(80) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        estado VARCHAR(16) NOT NULL DEFAULT 'PENDIENTE',
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ack (id_empresa, id_distribucion, terminal),
        INDEX idx_ack_dist (id_empresa, id_distribucion),
        INDEX idx_ack_term (id_empresa, terminal, estado)"""),

    # ── Configuracion de distribucion por empresa ───────────────────────────────
    ("distribucion_config", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        ventana_hora INT NOT NULL DEFAULT 3,
        ventana_activa TINYINT(1) NOT NULL DEFAULT 1,
        laboral_inicio INT NOT NULL DEFAULT 8,
        laboral_fin INT NOT NULL DEFAULT 22,
        reintentos_seg VARCHAR(160) NOT NULL DEFAULT '60,300,900,1800,3600,43200,86400',
        estrategia_conflicto VARCHAR(24) NOT NULL DEFAULT 'version_superior',
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_distcfg (id_empresa)"""),

    # ── Registro de conflictos de sincronizacion ────────────────────────────────
    ("distribucion_conflictos", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        entidad VARCHAR(60) NOT NULL,
        entidad_id VARCHAR(80) NOT NULL,
        estrategia VARCHAR(24) NOT NULL,
        version_local INT DEFAULT NULL,
        version_remota INT DEFAULT NULL,
        resolucion VARCHAR(16) NOT NULL,
        detalle VARCHAR(255) DEFAULT NULL,
        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_conf (id_empresa, entidad, entidad_id)"""),

    # ── Versionado LATERAL de entidades sincronizables (no altera tablas) ───────
    ("entidad_versiones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        entidad VARCHAR(60) NOT NULL,
        entidad_id VARCHAR(80) NOT NULL,
        version INT NOT NULL DEFAULT 1,
        revision INT NOT NULL DEFAULT 0,
        autor VARCHAR(80) DEFAULT NULL,
        origen VARCHAR(60) DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_entver (id_empresa, entidad, entidad_id),
        INDEX idx_entver (id_empresa, entidad)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
