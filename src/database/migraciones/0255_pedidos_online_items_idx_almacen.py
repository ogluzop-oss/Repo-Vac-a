"""Migración 0255 — Índice de soporte para el almacén de origen del encargo. ADITIVA,
idempotente, reversible.

NOTA IMPORTANTE (decisión de diseño, documentada tras auditar el esquema real): el plan
original de este punto preveía añadir una columna `id_almacen_origen` a `pedidos_online`. Al
verificar el esquema real se comprobó que esa columna YA EXISTE — a nivel de LÍNEA, no de
cabecera — como `pedidos_online_items.id_almacen` (migración 0166_pedido_online_almacen,
`ADD COLUMN IF NOT EXISTS id_almacen INT DEFAULT NULL`), y que YA está cableada de extremo a
extremo: `_VentaOnlineDialog` (`gui/tpv.py`) la rellena desde el stock físico por almacén
(`cmb_almacen`/`_poblar_almacenes`) y `crear_pedido_online` ya la persiste por línea
(`services/tpv/online_orders_service.py`). Añadir `pedidos_online.id_almacen_origen` habría
creado una SEGUNDA fuente de verdad para el mismo dato (violación directa del principio "un
solo motor" de este repositorio). Por eso esta migración NO añade esa columna: reutiliza
`pedidos_online_items.id_almacen` tal cual (ver `buscar_almacenes_con_stock`,
`confirmar_pago_encargo` y la visibilidad ampliada en `listar_pedidos_online`, todas en
`online_orders_service.py`).

Lo que SÍ falta y esta migración añade: un ÍNDICE sobre `pedidos_online_items.id_almacen`
(no existía; la columna se creó sin uno en 0166). Antes era un campo decorativo sin consultas
propias; ahora lo usan en caliente (a) el filtro de visibilidad por almacén de origen de
`listar_pedidos_online` (`EXISTS (SELECT 1 FROM pedidos_online_items WHERE id_pedido=... AND
id_almacen=...)`) y (b) cualquier futura pantalla de "pedidos que debo preparar" del propio
almacén — ambas filtran por `id_almacen` a escala, así que conviene indexarlo.
"""

VERSION = "0255"
DESCRIPCION = ("Índice pedidos_online_items(id_almacen) — soporta la visibilidad por almacén "
               "de origen (reutiliza la columna de 0166; no se duplica con una nueva en "
               "pedidos_online, ver docstring)")
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "pedidos_online_items"
_INDICE = "idx_poi_almacen"
_COLUMNA = "id_almacen"


def _existe_indice(cur) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND INDEX_NAME=%s", (_TABLA, _INDICE))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _existe_indice(cur):
        cur.execute(f"ALTER TABLE {_TABLA} ADD INDEX {_INDICE} ({_COLUMNA})")


def revertir(cur):
    if _existe_indice(cur):
        cur.execute(f"ALTER TABLE {_TABLA} DROP INDEX {_INDICE}")
