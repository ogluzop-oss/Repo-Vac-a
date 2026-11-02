"""
Migración 0270 — Artículos en consignación (Portal B2B, Fase 1): el proveedor puede marcar en su
catálogo B2B qué artículos ofrece también en modalidad de stock en consignación, con una comisión por
unidad que se factura ADEMÁS del precio del artículo cuando el comprador consume ese stock depositado
(ver `b2b_pedidos.registrar_consumo_consignacion`). ADITIVA, idempotente, reversible.

`b2b_catalogo.disponible_consignacion`/`comision_unitaria`: los declara el proveedor en su catálogo —
`comision_unitaria` solo tiene sentido si `disponible_consignacion=1` (mismo patrón condicional que
`es_perecedero` → `lote`/`fecha_caducidad` en esa misma tabla). `DEFAULT NULL` en `comision_unitaria`
(no 0) a propósito: distingue "no aplica" (artículo nunca ofrecido en consignación) de "0 € de comisión"
(ofrecido, pero sin coste adicional) — igual que `precio_unitario` no se reutiliza para esto.

`b2b_consignacion_saldo.comision_unitaria`: se CONGELA en el momento del depósito (mismo momento y
mismo criterio que ya usa esa tabla para `precio_unitario`, ver `b2b_pedidos._registrar_deposito_
consignacion`, migración 0269) — aquí sí usa `DEFAULT 0`, no NULL: cada fila de saldo representa un
depósito ya ocurrido y "0" es un valor real (comisión nula), no una ausencia de dato. Toda fila de saldo
creada ANTES de esta migración (o depositada desde un artículo sin comisión declarada) queda en 0 —
backward-compatible con `registrar_consumo_consignacion` (factura `precio_unitario + comision_unitaria`,
que para 0 es idéntico al importe de siempre).
"""

VERSION = "0270"
DESCRIPCION = ("Artículos en consignación: disponible_consignacion/comision_unitaria en b2b_catalogo + "
              "comision_unitaria congelada en b2b_consignacion_saldo")
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA_CAT = "b2b_catalogo"
_COL_CAT = [
    ("disponible_consignacion", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("comision_unitaria", "DECIMAL(12,4) DEFAULT NULL"),
]

_TABLA_SALDO = "b2b_consignacion_saldo"
_COL_SALDO = [("comision_unitaria", "DECIMAL(12,4) NOT NULL DEFAULT 0")]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _COL_CAT:
        if not _existe_columna(cur, _TABLA_CAT, col):
            cur.execute(f"ALTER TABLE {_TABLA_CAT} ADD COLUMN {col} {ddl}")
    for col, ddl in _COL_SALDO:
        if not _existe_columna(cur, _TABLA_SALDO, col):
            cur.execute(f"ALTER TABLE {_TABLA_SALDO} ADD COLUMN {col} {ddl}")


def revertir(cur):
    for col, _ddl in reversed(_COL_SALDO):
        if _existe_columna(cur, _TABLA_SALDO, col):
            cur.execute(f"ALTER TABLE {_TABLA_SALDO} DROP COLUMN {col}")
    for col, _ddl in reversed(_COL_CAT):
        if _existe_columna(cur, _TABLA_CAT, col):
            cur.execute(f"ALTER TABLE {_TABLA_CAT} DROP COLUMN {col}")
