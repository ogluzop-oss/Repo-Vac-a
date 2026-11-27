"""
Migración 0363 — Talla en equivalencias de referencia de proveedor (petición explícita,
2026-11-24): hasta ahora, `equivalencias_referencia_proveedor` solo admitía UNA equivalencia por
(empresa, proveedor, referencia) — si el mismo artículo de un proveedor tenía varias tallas que
comparten la misma referencia, registrar la talla M para esa referencia SOBRESCRIBÍA la
equivalencia de la talla S ya registrada (confirmado en `db/equivalencias_proveedor.py
::crear_equivalencia`, que hace UPDATE cuando la referencia ya existe). Añade `talla` a la clave
para que cada (referencia, talla) sea una equivalencia independiente — ver
`db/equivalencias_proveedor.py` para la resolución (automática si solo hay una talla registrada o
se indica explícitamente; ambigua si hay varias y no se indica, para que el llamador pregunte).
"""

VERSION = "0363"
DESCRIPCION = "Columna talla en equivalencias_referencia_proveedor (una equivalencia por referencia+talla)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
        "AND table_name=%s AND column_name=%s", (tabla, columna))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def _tiene_indice(cur, tabla, nombre) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() "
        "AND table_name=%s AND index_name=%s", (tabla, nombre))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "equivalencias_referencia_proveedor", "talla"):
        cur.execute("ALTER TABLE equivalencias_referencia_proveedor ADD COLUMN talla "
                   "VARCHAR(20) DEFAULT NULL AFTER referencia_proveedor")
    if _tiene_indice(cur, "equivalencias_referencia_proveedor", "uq_equiv_ref"):
        cur.execute("ALTER TABLE equivalencias_referencia_proveedor DROP INDEX uq_equiv_ref")
    if not _tiene_indice(cur, "equivalencias_referencia_proveedor", "uq_equiv_ref_talla"):
        cur.execute("ALTER TABLE equivalencias_referencia_proveedor ADD UNIQUE KEY "
                   "uq_equiv_ref_talla (id_empresa, id_proveedor, referencia_proveedor, talla)")


def revertir(cur):
    if _tiene_indice(cur, "equivalencias_referencia_proveedor", "uq_equiv_ref_talla"):
        cur.execute("ALTER TABLE equivalencias_referencia_proveedor DROP INDEX uq_equiv_ref_talla")
    if not _tiene_indice(cur, "equivalencias_referencia_proveedor", "uq_equiv_ref"):
        cur.execute("ALTER TABLE equivalencias_referencia_proveedor ADD UNIQUE KEY "
                   "uq_equiv_ref (id_empresa, id_proveedor, referencia_proveedor)")
    if _tiene_columna(cur, "equivalencias_referencia_proveedor", "talla"):
        cur.execute("ALTER TABLE equivalencias_referencia_proveedor DROP COLUMN talla")
