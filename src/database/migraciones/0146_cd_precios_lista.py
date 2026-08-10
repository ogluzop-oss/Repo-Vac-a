"""
Migración 0146 — PCD · Etapa B · Fase B4: listas de precios comerciales.

Pieza que FALTA en la gestión comercial (las promociones/cupones YA existen en db.promociones y
db.fidelizacion y se REUTILIZAN, N7). Permite un precio por lista/canal/segmento/moneda para un
artículo, variante o publicación. Si no hay entrada, se usa el precio base (degradable).

ADITIVA, idempotente, reversible. Multiempresa. No elimina ni altera datos.
"""

VERSION = "0146"
DESCRIPCION = "PCD Etapa B/F4: cd_precios_lista (listas de precios comerciales)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_precios_lista", """
        id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa  CHAR(36)              DEFAULT NULL,
        lista       VARCHAR(60)  NOT NULL,                 -- pvp|mayorista|canal_web|black_friday…
        referencia  VARCHAR(80)  NOT NULL,                 -- codigo artículo / sku variante / id_publicacion
        ambito      VARCHAR(20)  NOT NULL DEFAULT 'articulo', -- articulo|variante|publicacion
        canal       VARCHAR(40)           DEFAULT NULL,
        segmento    VARCHAR(40)           DEFAULT NULL,
        moneda      VARCHAR(8)   NOT NULL DEFAULT 'EUR',
        precio      DECIMAL(12,4) NOT NULL DEFAULT 0,
        activo      TINYINT      NOT NULL DEFAULT 1,
        ts_creado   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_actualizado DATETIME           DEFAULT NULL,
        UNIQUE KEY uq_precio_lista (id_empresa, lista, referencia, moneda),
        INDEX idx_precios_lista (id_empresa, lista),
        INDEX idx_precios_ref (id_empresa, referencia)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
