"""
Migración 0262 — Unificación de recepciones: los pedidos B2B pasan a recibirse desde el mismo motor
logístico que ya usan los traspasos internos (`documentos_logisticos`/`_pales`/`_lineas`), en vez de
confirmarse desde el Portal Empresa. ADITIVA, idempotente, reversible.

`documentos_logisticos.tipo_documento` YA admite cualquier VARCHAR(30) (el motor solo usaba 'TRASPASO'
hasta ahora); se introduce el valor 'B2B' sin tocar esa columna. Lo único que falta es un enlace de
vuelta a `transaccion_comercial.id_tx` (UUID, CHAR(36) — no cabe en `id_documento` VARCHAR(50) como
clave estructurada, y buscarlo por substring de `id_documento` sería frágil) para que la GUI de
Logística (`gui/recepcion_pale.py`) pueda distinguir en el escaneo si el documento es un pedido B2B
—y en tal caso delegar en `services.compras.b2b_pedidos.recibir_mercancia`, el motor oficial que YA
existía— o un traspaso interno (camino sin cambios, `db.logistica.procesar_recepcion_logistica`).
Mismo patrón exacto que 0223 (`compras_cancelaciones.id_tx`, columna nueva por el mismo motivo).
"""

VERSION = "0262"
DESCRIPCION = "Logística: documentos_logisticos.id_tx (enlace a pedidos B2B recibidos desde Logística)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "documentos_logisticos"
_COL = "id_tx"
_COL_DDL = "CHAR(36) DEFAULT NULL"
_IDX = "idx_dl_id_tx"


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
    if not _existe_columna(cur, _TABLA, _COL):
        cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {_COL} {_COL_DDL}")
    if not _existe_indice(cur, _TABLA, _IDX):
        cur.execute(f"ALTER TABLE {_TABLA} ADD INDEX {_IDX} ({_COL})")


def revertir(cur):
    if _existe_indice(cur, _TABLA, _IDX):
        cur.execute(f"ALTER TABLE {_TABLA} DROP INDEX {_IDX}")
    if _existe_columna(cur, _TABLA, _COL):
        cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {_COL}")
