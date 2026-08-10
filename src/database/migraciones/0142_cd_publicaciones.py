"""
Migración 0142 — PCD · Fase 7 (RFC-CD-001/002/004): Product Publication Layer (PPL).

Persistencia de la representación comercial reutilizable de un producto del ERP hacia cualquier canal.
La publicación NO es el producto: referencia el artículo ERP sin modificarlo. Versionado inmutable
(nunca se sobrescribe; rollback = versión nueva). i18n a nivel de dato (multi-idioma/región sin
duplicar la publicación).

  · cd_publicaciones          — cabecera (tipo/objetivo/estado/version_actual; referencia al ERP).
  · cd_publicacion_versiones  — versiones INMUTABLES (contenido/seo/media/origen). UNIQUE(pub,version).
  · cd_publicacion_i18n       — contenido localizado por (pub, version, idioma, region).

ADITIVA, idempotente, reversible. No elimina ni altera datos existentes (solo tablas nuevas).
"""

VERSION = "0142"
DESCRIPCION = "PCD Fase 7: Product Publication Layer (publicaciones + versiones + i18n)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_publicaciones", """
        id_publicacion  CHAR(36)     NOT NULL PRIMARY KEY,
        id_empresa      CHAR(36)              DEFAULT NULL,
        codigo_articulo VARCHAR(50)           DEFAULT NULL,    -- referencia al producto ERP (no lo modifica)
        tipo            VARCHAR(20)  NOT NULL DEFAULT 'producto',  -- producto|servicio|digital|pack|variante|…
        objetivo        VARCHAR(20)           DEFAULT NULL,    -- vender|branding|captacion|reservas|…
        estado          VARCHAR(16)  NOT NULL DEFAULT 'BORRADOR',
        version_actual  INT          NOT NULL DEFAULT 1,
        usuario         VARCHAR(120)          DEFAULT NULL,
        ts_creado       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_actualizado  DATETIME              DEFAULT NULL,
        INDEX idx_pub_art (id_empresa, codigo_articulo),
        INDEX idx_pub_estado (id_empresa, estado)"""),
    ("cd_publicacion_versiones", """
        id               BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_publicacion   CHAR(36)    NOT NULL,
        id_empresa       CHAR(36)             DEFAULT NULL,
        version          INT         NOT NULL,
        estado           VARCHAR(16)          DEFAULT NULL,     -- snapshot del estado al crear la versión
        objetivo         VARCHAR(20)          DEFAULT NULL,
        contenido        MEDIUMTEXT,                            -- representación comercial (JSON)
        seo              MEDIUMTEXT,                            -- titulo/descripcion/slug/metadatos/OG/… (JSON)
        media            MEDIUMTEXT,                            -- referencias de media (JSON; nunca ficheros)
        origen           VARCHAR(16) NOT NULL DEFAULT 'manual', -- manual|ia_propuesta
        correlation_id   VARCHAR(80)          DEFAULT NULL,
        communication_id VARCHAR(80)          DEFAULT NULL,
        actor            VARCHAR(120)         DEFAULT NULL,
        ts_creado        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_pub_version (id_publicacion, version),
        INDEX idx_ver_emp (id_empresa)"""),
    ("cd_publicacion_i18n", """
        id             BIGINT     NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_publicacion CHAR(36)   NOT NULL,
        version        INT        NOT NULL,
        id_empresa     CHAR(36)            DEFAULT NULL,
        idioma         VARCHAR(8) NOT NULL,
        region         VARCHAR(8) NOT NULL DEFAULT '',
        contenido      MEDIUMTEXT,                              -- contenido localizado (JSON)
        UNIQUE KEY uq_pub_i18n (id_publicacion, version, idioma, region),
        INDEX idx_i18n_emp (id_empresa)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
