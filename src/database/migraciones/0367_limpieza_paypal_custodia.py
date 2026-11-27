"""
Migración 0367 — Limpieza de columnas del modelo de custodia PayPal retirado (petición explícita,
2026-11-27: "elimina todo el código obsoleto que no se vaya a usar para esta nueva lógica").

Ninguna tiene datos reales todavía (confirmado en los docstrings de las migraciones 0358/0360 que
las crearon — `PAYPAL_CLIENT_ID` global nunca se usó para cobros B2B reales antes de este rediseño):

- `suministradores.paypal_email` / `paypal_merchant_id`: destino de los Payouts del modelo de
  custodia (migr. 0355/0358) — sustituidas por `paypal_client_id`/`paypal_client_secret` (migr.
  0366, credenciales PROPIAS del proveedor). Ya no se leen en ningún punto de la UI.
- `b2b_escrow.payout_proveedor_ref` / `payout_proveedor_estado`: seguimiento del Payout neto
  (migr. 0358) — ya no se escriben desde que `liberar_fondos` solo captura (el dinero nace
  directamente en la cuenta del proveedor, nunca hace falta un Payout posterior).
"""

VERSION = "0367"
DESCRIPCION = "Limpieza: columnas del modelo de custodia PayPal retirado"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLUMNAS = (
    ("suministradores", "paypal_email", "VARCHAR(255) DEFAULT NULL"),
    ("suministradores", "paypal_merchant_id", "VARCHAR(64) NULL"),
    ("b2b_escrow", "payout_proveedor_ref", "VARCHAR(160) DEFAULT NULL"),
    ("b2b_escrow", "payout_proveedor_estado", "VARCHAR(20) DEFAULT NULL"),
)


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
        "AND table_name=%s AND column_name=%s", (tabla, columna))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    for tabla, columna, _tipo in _COLUMNAS:
        if _tiene_columna(cur, tabla, columna):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {columna}")


def revertir(cur):
    for tabla, columna, tipo in _COLUMNAS:
        if not _tiene_columna(cur, tabla, columna):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
