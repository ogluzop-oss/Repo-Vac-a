"""
Migración 0137 — Fase VI · Bloque 13 Global SaaS Platform. ADITIVA, idempotente, reversible.

Añade SOLO lo nuevo (no duplica `planes_saas`/`facturas_saas`/`empresa_licencia`, que ya existen):
regiones, empresa→región, límites por plan/empresa, consumo y feature flags cloud. Multiempresa/
multi-región. Preparación (sin cobros ni despliegue real).
"""

VERSION = "0137"
DESCRIPCION = "Fase VI · Global SaaS: regiones, empresa_region, límites, consumo, feature flags cloud"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("saas_regiones", """
        codigo VARCHAR(8) NOT NULL PRIMARY KEY,          -- eu|am|as|af|oc
        nombre VARCHAR(80) NOT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP"""),
    ("empresa_region", """
        id_empresa CHAR(36) NOT NULL PRIMARY KEY,
        codigo_region VARCHAR(8) NOT NULL DEFAULT 'eu',
        cluster VARCHAR(80) DEFAULT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP"""),
    ("saas_limites", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,                -- NULL = límite por plan
        plan VARCHAR(24) DEFAULT NULL,
        recurso VARCHAR(40) NOT NULL,                    -- usuarios|tiendas|almacenes|correos|api|...
        limite BIGINT NOT NULL DEFAULT 0,                -- 0 = sin límite
        UNIQUE KEY uq_limite (id_empresa, plan, recurso),
        INDEX idx_limite (plan, recurso)"""),
    ("saas_consumo", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa CHAR(36) DEFAULT NULL,
        recurso VARCHAR(40) NOT NULL,
        valor BIGINT NOT NULL DEFAULT 0,
        periodo VARCHAR(16) DEFAULT NULL,                -- p. ej. 2026-07
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_consumo (id_empresa, recurso, periodo)"""),
    ("cloud_feature_flags", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        flag VARCHAR(80) NOT NULL,
        ambito VARCHAR(16) NOT NULL DEFAULT 'global',    -- global|region|empresa|plan|usuario
        ambito_id VARCHAR(64) DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 0,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_flag (flag, ambito, ambito_id),
        INDEX idx_flag (flag)"""),
]

_REGIONES = [("eu", "Europa"), ("am", "América"), ("as", "Asia"), ("af", "África"),
             ("oc", "Oceanía")]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    for codigo, nombre in _REGIONES:
        cur.execute("INSERT IGNORE INTO saas_regiones (codigo, nombre) VALUES (%s,%s)",
                    (codigo, nombre))


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
