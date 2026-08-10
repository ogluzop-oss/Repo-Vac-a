"""
Migración 0149 — PCD · Etapa B · Fase B8: automatización comercial (cd_campanas).

Define campañas/automatizaciones (feed, republicación, SEO, campaña) programables. La IA se REUTILIZA
vía el Presence Generator (solo propone; Workflow gobierna); la publicación a canales va por el Sync
Engine; la programación por el Scheduler. Aquí solo se define la automatización y se traza su ejecución.

ADITIVA, idempotente, reversible. Multiempresa. No elimina ni altera datos.
"""

VERSION = "0149"
DESCRIPCION = "PCD Etapa B/F8: cd_campanas (automatización comercial: feeds/republicación/SEO/campañas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_campanas", """
        id               BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa       CHAR(36)              DEFAULT NULL,
        nombre           VARCHAR(120) NOT NULL,
        tipo             VARCHAR(20)  NOT NULL DEFAULT 'feed',   -- feed|republicacion|seo|campana
        canal            VARCHAR(40)           DEFAULT NULL,
        objetivo         VARCHAR(20)           DEFAULT NULL,     -- vender|branding|campana|…
        parametros       MEDIUMTEXT,                             -- JSON (pais/idioma/moneda/publicaciones/tipos)
        programacion     VARCHAR(60)           DEFAULT NULL,     -- cron/frecuencia (Scheduler)
        estado           VARCHAR(16)  NOT NULL DEFAULT 'activa', -- activa|pausada|finalizada
        ultimo_run       DATETIME              DEFAULT NULL,
        ultimo_resultado MEDIUMTEXT,                             -- resumen de la última ejecución (JSON)
        actor            VARCHAR(120)          DEFAULT NULL,
        ts_creado        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_actualizado   DATETIME              DEFAULT NULL,
        INDEX idx_camp_estado (id_empresa, estado),
        INDEX idx_camp_tipo (id_empresa, tipo)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
