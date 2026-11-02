"""
Migración 0266 — Landed Cost (Fase A, cimientos comunes): snapshot ligero de coste landed sobre
`lotes`. ADITIVA, idempotente, reversible.

Un lote puede recibir varias entradas (`lotes.registrar_entrada` incrementa `cantidad`), así que un
coste landed fijo por fila de lote sería incoherente como desglose completo — el desglose auditable
real (base + cada componente indirecto = landed final, por línea y por recepción) vive en una tabla
hija propia de `compras_costes_extra` (Fase B). Aquí `lotes` solo gana un snapshot ligero: el coste
base, el coste indirecto acumulado y el coste landed final por unidad, más la referencia a la
recepción/transacción de origen que lo generó (compra vía `compras_recepciones` o pedido B2B vía
`transaccion_comercial`, de ahí los dos campos de origen separados). Mismo patrón exacto que
`0261_b2b_lote_caducidad.py` (guard `_existe_columna`, `aplicar`/`revertir` por lista de columnas).
"""

VERSION = "0266"
DESCRIPCION = "Landed Cost: snapshot de coste unitario base/indirecto/landed + origen en lotes"
REVERSIBLE = True
REQUIERE_BACKUP = False

_LOTES = [
    ("coste_unitario_base", "DECIMAL(12,4) DEFAULT NULL"),
    ("coste_unitario_indirecto", "DECIMAL(12,4) DEFAULT NULL"),
    ("coste_unitario_landed", "DECIMAL(12,4) DEFAULT NULL"),
    ("id_recepcion_origen", "BIGINT DEFAULT NULL"),
    ("id_tx_origen", "CHAR(36) DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _LOTES:
        if not _existe_columna(cur, "lotes", col):
            cur.execute(f"ALTER TABLE lotes ADD COLUMN {col} {ddl}")


def revertir(cur):
    for col, _ in reversed(_LOTES):
        if _existe_columna(cur, "lotes", col):
            cur.execute(f"ALTER TABLE lotes DROP COLUMN {col}")
