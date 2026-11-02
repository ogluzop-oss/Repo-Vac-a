"""
Migración 0261 — Smart Suppliers: lote/caducidad declarados por el PROVEEDOR en el catálogo B2B,
propagados al pedido. ADITIVA, idempotente, reversible.

Rediseño del flujo de datos de trazabilidad (Punto 3 bis): el lote/caducidad de un artículo
perecedero ya NO lo escribe el operario de Logística al recibir el palé — lo declara el PROVEEDOR
al publicar el artículo en su catálogo B2B (`b2b_catalogo`, migración 0219), y viaja con el pedido
(`transaccion_lineas`, migración 0221) para que la Empresa lo vea ya conocido al recibir la
mercancía. Sigue el MISMO patrón aditivo exacto que 0221 (columnas nuevas, sin tocar ninguna
existente, sin motor paralelo).

`transaccion_comercial.stock_recibido_en` es el marcador de idempotencia de la recepción física
de stock de un pedido B2B (`services.compras.b2b_pedidos.recibir_mercancia`) — una acción NUEVA y
DISTINTA de la confirmación de entrega del escrow (`b2b_escrow.confirmar_entrega`, que libera
fondos y no toca stock/lotes en absoluto hoy). Se registra aparte para no tocar `b2b_escrow.py`.
"""

VERSION = "0261"
DESCRIPCION = "Smart Suppliers: perecedero/lote/caducidad en catálogo B2B + transaccion_lineas + marca de recepción de stock"
REVERSIBLE = True
REQUIERE_BACKUP = False

_CATALOGO = [
    ("es_perecedero", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("lote", "VARCHAR(80) DEFAULT NULL"),
    ("fecha_caducidad", "DATE DEFAULT NULL"),
]
_LINEAS = [
    ("lote", "VARCHAR(80) DEFAULT NULL"),
    ("fecha_caducidad", "DATE DEFAULT NULL"),
]
_TX = [
    ("stock_recibido_en", "DATETIME DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _CATALOGO:
        if not _existe_columna(cur, "b2b_catalogo", col):
            cur.execute(f"ALTER TABLE b2b_catalogo ADD COLUMN {col} {ddl}")
    for col, ddl in _LINEAS:
        if not _existe_columna(cur, "transaccion_lineas", col):
            cur.execute(f"ALTER TABLE transaccion_lineas ADD COLUMN {col} {ddl}")
    for col, ddl in _TX:
        if not _existe_columna(cur, "transaccion_comercial", col):
            cur.execute(f"ALTER TABLE transaccion_comercial ADD COLUMN {col} {ddl}")


def revertir(cur):
    for col, _ in reversed(_TX):
        if _existe_columna(cur, "transaccion_comercial", col):
            cur.execute(f"ALTER TABLE transaccion_comercial DROP COLUMN {col}")
    for col, _ in reversed(_LINEAS):
        if _existe_columna(cur, "transaccion_lineas", col):
            cur.execute(f"ALTER TABLE transaccion_lineas DROP COLUMN {col}")
    for col, _ in reversed(_CATALOGO):
        if _existe_columna(cur, "b2b_catalogo", col):
            cur.execute(f"ALTER TABLE b2b_catalogo DROP COLUMN {col}")
