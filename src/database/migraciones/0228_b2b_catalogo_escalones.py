"""
Migración 0228 — Precios escalonados por volumen / rappels (Smart Suppliers B2B · Fase 3).

Un artículo del catálogo B2B (`b2b_catalogo`) puede tener 0..N escalones de precio por cantidad; el
`precio_unitario` de `b2b_catalogo` sigue siendo el precio "piso" (válido desde el MOQ). ADITIVA,
idempotente, reversible.
"""

VERSION = "0228"
DESCRIPCION = "Escalones de precio por volumen del catálogo B2B (rappels)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = ("b2b_catalogo_escalones", """
    id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_articulo     BIGINT        NOT NULL,
    cantidad_desde  INT           NOT NULL,
    precio_unitario DECIMAL(12,4) NOT NULL,
    UNIQUE KEY uq_b2b_escalon (id_articulo, cantidad_desde),
    CONSTRAINT fk_b2b_escalon_articulo FOREIGN KEY (id_articulo)
        REFERENCES b2b_catalogo (id) ON DELETE CASCADE""")


def aplicar(cur):
    nombre, cols = _TABLA
    cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute(f"DROP TABLE IF EXISTS {_TABLA[0]}")
