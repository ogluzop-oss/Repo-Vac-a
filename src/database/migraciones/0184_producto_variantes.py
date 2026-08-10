"""
Migración 0183 — Variantes de producto por TALLA y COLOR (edición Textil). ADITIVA, idempotente, reversible.

Un producto "modelo" (p. ej. una camiseta) se despliega en VARIANTES (talla × color); cada variante es un SKU
propio en `articulos` (con su stock/precio/código de barras), enlazado al modelo padre por `producto_variantes`.
Reutiliza el modelo de artículos/stock existente (N7). AISLAMIENTO por `id_empresa`.
"""

VERSION = "0184"
DESCRIPCION = "Textil: producto_variantes (variantes por talla/color enlazadas al modelo padre)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS producto_variantes (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa CHAR(36) DEFAULT NULL,
            codigo_padre VARCHAR(64) NOT NULL,
            codigo_variante VARCHAR(64) NOT NULL,
            talla VARCHAR(32) DEFAULT NULL,
            color VARCHAR(32) DEFAULT NULL,
            creado DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_var (id_empresa, codigo_variante),
            INDEX idx_var_padre (id_empresa, codigo_padre)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS producto_variantes")
