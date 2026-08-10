"""
Migración 0187 — `familias_producto.restringida` (consolidación de categorización de producto). ADITIVA,
idempotente, reversible.

La FAMILIA (`articulos.id_familia` → `familias_producto`) es la fuente ÚNICA de categorización de producto.
Este flag marca una familia como de VENTA RESTRINGIDA (verificación de edad: alcohol/tabaco…), sustituyendo a
los antiguos campos libres `articulos.seccion`/`articulos.categoria` (que quedan en desuso). Lo consume el
autocobro (`services/tpv/self_checkout_service`).
"""

VERSION = "0187"
DESCRIPCION = "familias_producto.restringida (venta restringida / verificación de edad)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return bool((r[0] if not isinstance(r, dict) else list(r.values())[0]))


def aplicar(cur):
    if not _tiene_columna(cur, "familias_producto", "restringida"):
        cur.execute("ALTER TABLE familias_producto ADD COLUMN restringida TINYINT(1) NOT NULL DEFAULT 0")


def revertir(cur):
    if _tiene_columna(cur, "familias_producto", "restringida"):
        cur.execute("ALTER TABLE familias_producto DROP COLUMN restringida")
