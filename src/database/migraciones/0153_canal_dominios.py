"""
Migración 0153 — Canal Web · Dominios. ADITIVA, idempotente, reversible.

Añade `cd_canal_dominios`: los dominios/subdominios asociados a los canales web de una empresa (propio /
subdominio Smart Manager / comprado). Multiempresa estricto (clave por `id_empresa`, NUNCA por dominio).
Cada empresa puede tener varios dominios; uno marcado `activo`. Reutiliza `cd_canal_web` (el dominio
activo se refleja en `cd_canal_web.dominio`). No crea motor de dominios: es la persistencia de la capa de
dominios del Canal Web.
"""

VERSION = "0153"
DESCRIPCION = "Canal Web: cd_canal_dominios (propio/subdominio/comprado + DNS/HTTPS)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = ("cd_canal_dominios", """
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_empresa VARCHAR(64) NOT NULL,
    dominio VARCHAR(255) NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'propio',
    proveedor VARCHAR(60) DEFAULT NULL,
    referencia VARCHAR(160) DEFAULT NULL,
    precio DECIMAL(10,2) DEFAULT NULL,
    moneda VARCHAR(8) DEFAULT 'EUR',
    fecha_registro DATETIME DEFAULT NULL,
    fecha_expiracion DATETIME DEFAULT NULL,
    estado_dns VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    estado_https VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    renovacion_auto TINYINT NOT NULL DEFAULT 0,
    activo TINYINT NOT NULL DEFAULT 0,
    creado DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_emp_dominio (id_empresa, dominio),
    INDEX idx_cd_emp (id_empresa, activo)
""")


def aplicar(cur):
    nombre, cols = _TABLA
    cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cd_canal_dominios")
