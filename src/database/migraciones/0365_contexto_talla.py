"""
Migración 0365 — Columna `contexto_talla` en `producto_variantes` y en
`equivalencias_referencia_proveedor` (petición explícita, 2026-11-27: estructura de tallas por
tipo de artículo/familia demográfica/subfamilia/género con equivalencias EU/US/UK).

La talla en sí sigue guardándose igual que siempre (columna `talla`, ahora con la etiqueta EU
como valor canónico) — esta columna NUEVA solo guarda de qué tabla de `services.tallas` viene,
como `"TIPO|FAMILIA|SUBFAMILIA|GENERO"` (ver `services/tallas.py::contexto`). Es necesaria porque
una misma etiqueta EU (p. ej. "38") es a la vez una talla válida de calzado de mujer y de ropa de
mujer — sin el contexto no se podría saber qué tabla usar para convertir a US/UK sin arriesgarse a
adivinar mal. Aditiva y reversible; las filas existentes quedan con `contexto_talla=NULL` (se
siguen resolviendo con el método "best-effort" de `services.tallas.localizar_sin_contexto`, igual
de honesto que `equivalencias_proveedor.resolver_por_referencia` ante la ambigüedad).
"""

VERSION = "0365"
DESCRIPCION = "Columna contexto_talla en producto_variantes y equivalencias_referencia_proveedor"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = ("producto_variantes", "equivalencias_referencia_proveedor")


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
        "AND table_name=%s AND column_name=%s", (tabla, columna))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    for tabla in _TABLAS:
        if not _tiene_columna(cur, tabla, "contexto_talla"):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN contexto_talla VARCHAR(48) DEFAULT NULL "
                       "AFTER talla")


def revertir(cur):
    for tabla in _TABLAS:
        if _tiene_columna(cur, tabla, "contexto_talla"):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN contexto_talla")
