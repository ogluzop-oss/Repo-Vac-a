"""
Migracion 0092 — Motor de Automatizacion Empresarial (Paquete Enterprise 4). ADITIVA,
idempotente, reversible. NO toca ninguna tabla existente ni crea un segundo Workflow/BPM: solo
persiste las REGLAS (configurables/priorizadas/versionables) y el LOG de EJECUCIONES (auditoria,
panel y explicabilidad). Las acciones reutilizan Workflow/notificaciones/propuestas existentes.
Multiempresa/multitienda/SaaS.
"""

VERSION = "0092"
DESCRIPCION = "Automatizacion: automatizaciones_reglas, automatizaciones_ejecuciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("automatizaciones_reglas", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) NOT NULL,
        nombre VARCHAR(160) DEFAULT NULL,
        descripcion VARCHAR(255) DEFAULT NULL,
        trigger_tipo VARCHAR(16) NOT NULL DEFAULT 'programado',
        trigger_valor VARCHAR(60) DEFAULT NULL,
        condicion VARCHAR(60) NOT NULL,
        accion VARCHAR(60) NOT NULL,
        params MEDIUMTEXT DEFAULT NULL,
        nivel VARCHAR(16) NOT NULL DEFAULT 'proponer',
        prioridad VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
        activa TINYINT(1) NOT NULL DEFAULT 1,
        version INT NOT NULL DEFAULT 1,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_regla (id_empresa, codigo),
        INDEX idx_regla_trg (trigger_tipo, trigger_valor, activa)"""),

    ("automatizaciones_ejecuciones", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        id_tienda INT NOT NULL DEFAULT 0,
        codigo_regla VARCHAR(60) NOT NULL,
        trigger_tipo VARCHAR(16) DEFAULT NULL,
        trigger_ref VARCHAR(120) DEFAULT NULL,
        accion VARCHAR(60) DEFAULT NULL,
        nivel VARCHAR(16) DEFAULT NULL,
        estado VARCHAR(16) NOT NULL DEFAULT 'PROPUESTA',
        motivo VARCHAR(255) DEFAULT NULL,
        usuario VARCHAR(80) DEFAULT NULL,
        ref_entidad VARCHAR(60) DEFAULT NULL,
        ref_id VARCHAR(80) DEFAULT NULL,
        resultado VARCHAR(255) DEFAULT NULL,
        hash VARCHAR(64) DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_ejec (id_empresa, hash),
        INDEX idx_ejec (id_empresa, estado, creado),
        INDEX idx_ejec_regla (id_empresa, codigo_regla, creado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    # Siembra el catalogo semilla de reglas (idempotente, best-effort).
    try:
        from src.services.automatizacion import reglas as _R
        _R.sembrar(cur)
    except Exception:
        pass


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
