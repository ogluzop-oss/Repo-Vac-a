"""
Migración 0152 — Módulo Canal Web (entidad de negocio del canal). ADITIVA, idempotente, reversible.

Añade la capa que faltaba: el CANAL WEB como entidad con estado (no_configurado/generando/publicado/
despublicado/error), dominio, endpoint y la CONFIGURACIÓN DE NEGOCIO (JSON). No sustituye nada: reutiliza
`cd_conexiones` (endpoint/credenciales cifradas), `publicaciones`, `catalogo`, `sync`, `pickup`, etc.
Una fila por empresa (multiempresa estricto). `config_negocio` guarda TODA la configuración de negocio
—incluidos campos preparados para el futuro (horarios de recogida, capacidad, múltiples puntos)— sin
lógica operativa asociada todavía, para no volver a tocar el modelo de datos.
"""

VERSION = "0152"
DESCRIPCION = "Canal Web: entidad cd_canal_web (estado + dominio + config de negocio JSON)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = ("cd_canal_web", """
    id_empresa VARCHAR(64) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'no_configurado',
    dominio VARCHAR(255) DEFAULT NULL,
    endpoint VARCHAR(255) DEFAULT NULL,
    config_negocio MEDIUMTEXT DEFAULT NULL,
    generado_en DATETIME DEFAULT NULL,
    publicado_en DATETIME DEFAULT NULL,
    ultima_sync DATETIME DEFAULT NULL,
    actor VARCHAR(80) DEFAULT NULL,
    ts_creado DATETIME DEFAULT CURRENT_TIMESTAMP,
    ts_actualizado DATETIME DEFAULT NULL,
    PRIMARY KEY (id_empresa),
    INDEX idx_cw_estado (estado)
""")


def aplicar(cur):
    nombre, cols = _TABLA
    cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cd_canal_web")
