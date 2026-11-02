"""Migración 0254 — Geolocalización de almacenes. ADITIVA, idempotente, reversible.

Añade `latitud`/`longitud` a `almacen` — mismo patrón exacto que `clientes.latitud/longitud`
(migración 0102_crm_enriquecimiento.py: `DECIMAL(10,7) DEFAULT NULL`). `almacen` es la tabla
correcta (cubre tanto los almacenes `tipo_almacen='tienda'` como `central`/`regional`/
`logistico`), no `tiendas`: la proximidad se calcula entre almacenes reales de stock físico
(`stock_almacen`), no entre puntos de venta.

Prerrequisito para `services.tpv.online_orders_service.buscar_almacenes_con_stock` (ordena
almacenes con existencias por distancia haversine, ver `services/geo/distancia.py`).
"""

VERSION = "0254"
DESCRIPCION = "Geolocalización de almacenes: almacen.latitud/longitud"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLUMNAS = [
    ("almacen", "latitud", "DECIMAL(10,7) DEFAULT NULL"),
    ("almacen", "longitud", "DECIMAL(10,7) DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for tabla, col, definicion in _COLUMNAS:
        if not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")


def revertir(cur):
    for tabla, col, _ in reversed(_COLUMNAS):
        if _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
