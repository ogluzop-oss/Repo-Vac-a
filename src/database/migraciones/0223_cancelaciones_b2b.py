"""
Migración 0223 — Smart Suppliers · Fase D: enlazar `compras_cancelaciones` con pedidos B2B. ADITIVA,
idempotente, reversible.

`compras_cancelaciones.id_pedido` es BIGINT (pedidos legacy de `db.compras`); las Transacciones
Comerciales B2B usan un UUID (`transaccion_comercial.id_tx`, CHAR(36)) que no cabe en esa columna. Se
añade `id_tx` como columna NUEVA en vez de cambiar el tipo de `id_pedido` — no se toca nada existente,
y el sistema de strikes (`cancelaciones.strikes`) sigue contando filas de ambos orígenes por igual.
"""

VERSION = "0223"
DESCRIPCION = "Smart Suppliers: compras_cancelaciones.id_tx (enlace a pedidos B2B, UUID)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [("id_tx", "CHAR(36) DEFAULT NULL")]


def aplicar(cur):
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE compras_cancelaciones ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE compras_cancelaciones DROP COLUMN IF EXISTS {col}")
