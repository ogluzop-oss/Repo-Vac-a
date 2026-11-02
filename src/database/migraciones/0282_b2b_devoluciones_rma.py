"""
Migración 0282 — Smart Suppliers: RMA de autoservicio del comprador B2B (última pieza del paquete
Holded/Shopify-inspired de esta sesión). ADITIVA, idempotente, reversible.

Tres cambios:

1. `compras_devoluciones.estado` se ENSANCHA de VARCHAR(12) a VARCHAR(24): el nuevo valor inicial
   'pendiente_aprobacion' (21 caracteres) no cabe en la columna original (pensada solo para
   'registrada'/'anulada'...). Ensanchar una columna existente es seguro y no destructivo (no se
   pierde ningún valor ya almacenado); se hace con MODIFY COLUMN, no con ADD COLUMN, así que no es
   idempotente por "IF NOT EXISTS" sino porque re-ejecutar el mismo MODIFY con el mismo tipo es un
   no-op seguro.
2. `compras_devoluciones.id_tx` (CHAR(36), enlace a `transaccion_comercial.id_tx`) + `motivo_rechazo`
   (VARCHAR(255)) — MISMO patrón ya usado en 0223 (`compras_cancelaciones.id_tx`) y 0262
   (`documentos_logisticos.id_tx`): un pedido B2B usa un UUID que no cabe en las columnas BIGINT
   legacy (`id_pedido`), así que se enlaza con una columna nueva en vez de forzar el tipo existente.
   Sin `id_tx` no hay forma de, al aprobar un RMA, volver a encontrar el escrow/pedido B2B del que
   salió la devolución.
3. `transporte_recogidas` — orden de RECOGIDA (pickup, "entrega inversa": origen=nuestro almacén,
   destino=proveedor) para la mercancía de un RMA ya aprobado. Deliberadamente NO reutiliza
   `transporte_rutas`/`transporte_paradas` (esas tablas modelan reparto de SALIDA multi-parada con
   descuento de stock vía `salida_stock_oficial` al entregar — una recogida es de UN único punto, no
   vuelve a tocar stock porque el efecto de stock de la devolución ya se aplicó al aprobar el RMA
   —`db.compras.aprobar_devolucion`— y conceptualmente es lo inverso de una entrega, no una entrega
   más). Máquina de estados mínima y honesta: pendiente → recogido → recibido. Ver
   `services/transporte.py::generar_orden_recogida` (juicio documentado ahí también).
"""

VERSION = "0282"
DESCRIPCION = "Smart Suppliers: RMA autoservicio (compras_devoluciones pendiente_aprobacion/id_tx) + transporte_recogidas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA_DEV = "compras_devoluciones"
_COLS_DEV = [("id_tx", "CHAR(36) DEFAULT NULL"),
            ("motivo_rechazo", "VARCHAR(255) DEFAULT NULL")]
_IDX_DEV = "idx_devol_id_tx"


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
    # 1) Ensanchar estado (no destructivo: MODIFY preserva los valores ya almacenados).
    cur.execute(f"ALTER TABLE {_TABLA_DEV} MODIFY COLUMN estado VARCHAR(24) NOT NULL "
               "DEFAULT 'registrada'")
    # 2) Columnas nuevas de enlace/alegación.
    for col, ddl in _COLS_DEV:
        if not _existe_columna(cur, _TABLA_DEV, col):
            cur.execute(f"ALTER TABLE {_TABLA_DEV} ADD COLUMN {col} {ddl}")
    if not _existe_indice(cur, _TABLA_DEV, _IDX_DEV):
        cur.execute(f"ALTER TABLE {_TABLA_DEV} ADD INDEX {_IDX_DEV} (id_tx)")
    # 3) Orden de recogida (pickup) — reverse delivery mínima.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transporte_recogidas (
            id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)     NOT NULL,
            id_devolucion   BIGINT                DEFAULT NULL,
            id_tx           CHAR(36)              DEFAULT NULL,
            id_proveedor    BIGINT                DEFAULT NULL,
            direccion_origen  VARCHAR(255)        DEFAULT NULL,
            direccion_destino VARCHAR(255)        DEFAULT NULL,
            estado          VARCHAR(12)  NOT NULL DEFAULT 'pendiente',  -- pendiente|recogido|recibido
            notas           VARCHAR(255)          DEFAULT NULL,
            usuario         VARCHAR(120)          DEFAULT NULL,
            creado_en       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            recogido_en     DATETIME              DEFAULT NULL,
            recibido_en     DATETIME              DEFAULT NULL,
            INDEX idx_trec_empresa (id_empresa, estado),
            INDEX idx_trec_devolucion (id_devolucion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS transporte_recogidas")
    if _existe_indice(cur, _TABLA_DEV, _IDX_DEV):
        cur.execute(f"ALTER TABLE {_TABLA_DEV} DROP INDEX {_IDX_DEV}")
    for col, _ddl in _COLS_DEV:
        if _existe_columna(cur, _TABLA_DEV, col):
            cur.execute(f"ALTER TABLE {_TABLA_DEV} DROP COLUMN {col}")
    cur.execute(f"ALTER TABLE {_TABLA_DEV} MODIFY COLUMN estado VARCHAR(12) NOT NULL "
               "DEFAULT 'registrada'")
