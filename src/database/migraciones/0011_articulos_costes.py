"""
Migración 0011 — Costes de compra en artículos (E2.4). ADITIVA y reversible.

Añade a `articulos` los costes de aprovisionamiento, SIN tocar `precio` (PVP) ni el
resto del catálogo:
  - ultimo_coste : coste unitario de la última recepción.
  - coste_actual : coste vigente (= último, por defecto).
  - coste_medio  : coste medio ponderado por existencias.

Idempotente (comprueba la columna). No afecta a TPV/ventas/fiscal.
"""

VERSION = "0011"
DESCRIPCION = "Costes de compra en articulos (ultimo_coste, coste_actual, coste_medio)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col in ("ultimo_coste", "coste_actual", "coste_medio"):
        if not _tiene_columna(cur, "articulos", col):
            cur.execute(f"ALTER TABLE articulos ADD COLUMN {col} DECIMAL(10,2) NOT NULL DEFAULT 0")


def revertir(cur):
    for col in ("coste_medio", "coste_actual", "ultimo_coste"):
        if _tiene_columna(cur, "articulos", col):
            cur.execute(f"ALTER TABLE articulos DROP COLUMN {col}")
