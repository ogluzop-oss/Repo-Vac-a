"""
Migración 0145 — PCD · Etapa B · Fase B3: variantes del Catálogo Comercial Global.

Variantes comerciales (talla/color/formato…) asociadas a una publicación de la Product Publication
Layer. El precio/impuesto/moneda se COMPONEN en runtime reutilizando multidivisa y fiscalidad
existentes; aquí solo se guarda la variante y su delta de precio.

ADITIVA, idempotente, reversible. Multiempresa. No elimina ni altera datos.
"""

VERSION = "0145"
DESCRIPCION = "PCD Etapa B/F3: cd_catalogo_variantes (variantes de publicación)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_catalogo_variantes", """
        id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_publicacion CHAR(36)     NOT NULL,
        id_empresa     CHAR(36)              DEFAULT NULL,
        sku            VARCHAR(80)  NOT NULL,
        atributos      MEDIUMTEXT,                             -- {talla,color,…} (JSON)
        precio_delta   DECIMAL(12,4) NOT NULL DEFAULT 0,       -- suma/resta sobre el precio base
        codigo_articulo VARCHAR(50)          DEFAULT NULL,     -- referencia opcional al ERP
        activo         TINYINT      NOT NULL DEFAULT 1,
        orden          INT          NOT NULL DEFAULT 0,
        ts_creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_variante (id_publicacion, sku),
        INDEX idx_var_emp (id_empresa)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
