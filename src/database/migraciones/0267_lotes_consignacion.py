"""
Migración 0267 — Stock en Consignación (Fase A, cimientos comunes): marca de propiedad sobre
`lotes`. ADITIVA, idempotente, reversible.

Un lote recibido en consignación NUNCA genera pasivo/factura al recibirse — sigue siendo propiedad
del proveedor hasta que se consume (`lotes.consumir_fefo`, Fase C). `propiedad` distingue
'propio'/'consignacion' por fila de lote (todo lote existente hoy queda 'propio' por el DEFAULT,
cero impacto retroactivo); `id_suministrador` referencia al proveedor dueño de la mercancía mientras
esté en consignación — se guarda en el propio lote (no solo en el ledger de saldo de la Fase C)
porque `consumir_fefo` necesita saber a qué proveedor facturar en el momento del consumo sin tener
que reconsultar la transacción de origen. Índice `idx_lotes_propiedad` para el filtro habitual
"lotes en consignación de este artículo" sin table scan — mismo patrón de guard de índice que
`0262_logistica_b2b.py` (`_existe_indice`). Mismo idioma aditivo que `0261_b2b_lote_caducidad.py`.
"""

VERSION = "0267"
DESCRIPCION = "Stock en Consignación: propiedad/id_suministrador en lotes + índice idx_lotes_propiedad"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "lotes"
_COLS = [
    ("propiedad", "VARCHAR(20) NOT NULL DEFAULT 'propio'"),
    ("id_suministrador", "BIGINT DEFAULT NULL"),
]
_IDX = "idx_lotes_propiedad"
_IDX_COL = "propiedad"


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def _existe_indice(cur, tabla, indice) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND INDEX_NAME=%s", (tabla, indice))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _COLS:
        if not _existe_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {col} {ddl}")
    if not _existe_indice(cur, _TABLA, _IDX):
        cur.execute(f"ALTER TABLE {_TABLA} ADD INDEX {_IDX} ({_IDX_COL})")


def revertir(cur):
    if _existe_indice(cur, _TABLA, _IDX):
        cur.execute(f"ALTER TABLE {_TABLA} DROP INDEX {_IDX}")
    for col, _ in reversed(_COLS):
        if _existe_columna(cur, _TABLA, col):
            cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {col}")
