"""
Migración 0306 — Imágenes reales para productos y familias a granel. ADITIVA, idempotente,
reversible.

Sustituye el emoji por una imagen subida por el superadministrador: `productos_granel.imagen`
(ruta del fichero, mismo patrón ya usado por `articulos.imagen` — ruta en BD, bytes en
`documentos/`, nunca BLOB) + tabla `familias_granel_imagenes` (las 9 familias a granel son
código fijo en `services.tpv.familias_granel`, no filas de BD, así que necesitan su propia tabla
pequeña para guardar la imagen elegida por familia). Sin `id_empresa`: igual que
`productos_granel` (tabla ya global/sin multi-tenant, confirmado en `bootstrap_mariadb.sql`).
"""

VERSION = "0306"
DESCRIPCION = ("Imágenes de productos/familias a granel: productos_granel.imagen + tabla "
               "familias_granel_imagenes")
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE productos_granel ADD COLUMN IF NOT EXISTS imagen VARCHAR(500) DEFAULT NULL")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS familias_granel_imagenes (
            codigo_familia VARCHAR(40) PRIMARY KEY,
            ruta_imagen    VARCHAR(500) NOT NULL,
            actualizado    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS familias_granel_imagenes")
    cur.execute("ALTER TABLE productos_granel DROP COLUMN IF EXISTS imagen")
