"""
Migración 0234 — Tablas del SERVIDOR CENTRAL de licencias (proyecto de infraestructura SaaS
central — Fase 2, ver plan). Solo tienen sentido aplicadas sobre la base de datos CENTRAL
(`src/backend_central/`), nunca sobre la base de datos LOCAL de un cliente — pero se registran en
la misma secuencia de migraciones (reutilizando `db.migrador`, sin un sistema de migraciones
paralelo); en una instalación local quedan simplemente sin usar, dos tablas vacías de más.

- `codigos_activacion`: los códigos que el fundador genera al vender una licencia (un solo uso).
- `instalaciones_centrales`: qué `installation_id` (ver `services/licencia_central/identidad.py`)
  corresponde a qué empresa/cliente en la BD central, y sus credenciales M2M (`client_id`; el
  `client_secret` NUNCA se guarda, solo su hash, vía `services.api_publica.developer`, reutilizado).
"""

VERSION = "0234"
DESCRIPCION = "Tablas del servidor central de licencias: códigos de activación e instalaciones"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("codigos_activacion", """
        id              INT AUTO_INCREMENT PRIMARY KEY,
        codigo          VARCHAR(40)  NOT NULL,
        plan            VARCHAR(30)  NOT NULL,
        usado           TINYINT(1)   NOT NULL DEFAULT 0,
        id_empresa_creada CHAR(36)   NULL,
        generado_en     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        usado_en        DATETIME     NULL,
        UNIQUE KEY uq_codigo_activacion (codigo)"""),
    ("instalaciones_centrales", """
        id                  INT AUTO_INCREMENT PRIMARY KEY,
        installation_id     CHAR(36)     NOT NULL,
        id_empresa_central  CHAR(36)     NOT NULL,
        nombre_empresa      VARCHAR(255) NULL,
        client_id           VARCHAR(80)  NULL,
        fecha_alta          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ultima_verificacion DATETIME     NULL,
        UNIQUE KEY uq_installation_id (installation_id),
        INDEX idx_inst_central_empresa (id_empresa_central)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
