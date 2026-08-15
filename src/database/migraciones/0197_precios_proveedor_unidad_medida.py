"""
Migración 0197 — Bolsa de proveedores (Fase 1): unidad de medida en las tarifas de proveedor.
ADITIVA, idempotente, reversible.

Reutiliza la tabla EXISTENTE `proveedor_precios_negociados` (migr 0103, servicio `proveedores_pro`)
como base de la "bolsa de proveedores": el mismo artículo puede tener varias tarifas de un proveedor
según la UNIDAD DE MEDIDA (por unidad, caja, palé o peso/kg). Se añade la columna `unidad_medida` para
distinguirlas; por defecto 'unidad' (compatibilidad con lo ya cargado). No se crea ninguna tabla nueva.
"""

VERSION = "0197"
DESCRIPCION = "proveedor_precios_negociados: columna unidad_medida (unidad/caja/pale/kg) para la bolsa"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "proveedor_precios_negociados"


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, _TABLA, "unidad_medida"):
        cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN unidad_medida VARCHAR(12) NOT NULL DEFAULT 'unidad'")


def revertir(cur):
    if _tiene_columna(cur, _TABLA, "unidad_medida"):
        cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN unidad_medida")
