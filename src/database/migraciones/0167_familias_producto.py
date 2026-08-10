"""
Migración 0167 — Familias de producto. ADITIVA e IDEMPOTENTE.

Crea `familias_producto` (vocabulario de familias gestionable por empresa) y añade `id_familia` a
`articulos` (vínculo GLOBAL producto → familia). No modifica datos existentes (columna NULL).
"""

VERSION = "0167"
DESCRIPCION = "Familias de producto: tabla familias_producto + columna articulos.id_familia"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS familias_producto (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  DEFAULT NULL,
            nombre      VARCHAR(120) NOT NULL,
            descripcion VARCHAR(255)          DEFAULT NULL,
            color       VARCHAR(9)            DEFAULT NULL,
            orden       INT          NOT NULL DEFAULT 0,
            activo      TINYINT(1)   NOT NULL DEFAULT 1,
            creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fam_empresa (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS id_familia INT DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE articulos DROP COLUMN IF EXISTS id_familia")
    cur.execute("DROP TABLE IF EXISTS familias_producto")
