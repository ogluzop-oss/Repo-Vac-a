"""
Migración 0269 — Stock en Consignación (Fase C): flag `es_consignacion` en `transaccion_comercial` +
ledger de saldo/movimientos de consignación B2B. ADITIVA, idempotente, reversible.

Un pedido B2B en consignación (`es_consignacion=1`) recibe mercancía que sigue siendo propiedad del
proveedor (Fase A, `lotes.propiedad='consignacion'`) hasta que se CONSUME — la recepción física NUNCA
genera pasivo/factura (nunca pasa por escrow, `b2b_escrow.py` no se toca). `b2b_consignacion_saldo` es
el ledger agregado por (pedido de depósito × artículo): `cantidad_disponible` se deriva SIEMPRE
(`depositada - consumida - devuelta`) y NUNCA se almacena, para que no pueda desincronizarse de sus
tres componentes.

`b2b_consignacion_movimientos` es el ledger append-only de eventos (DEPOSITO/CONSUMO/DEVOLUCION/
LIQUIDACION). Un evento de consumo real (`lotes.consumir_fefo` → `b2b_pedidos.registrar_consumo_
consignacion`) puede repartirse ENTRE VARIOS `id_tx` de depósito (FIFO por antigüedad, el más
antiguo primero, si uno solo no cubre la cantidad) — así que el reclamo de idempotencia de la fila
`LIQUIDACION` NO puede anclarse a un `id_tx` concreto: cuál de los depósitos acaba siendo el
"principal" del reparto depende del saldo disponible EN ESE MOMENTO, que cambia entre la llamada
original y un reintento (si el primer depósito ya se agotó, un reintento repartiría desde el
siguiente). Anclar la clave a `id_tx` haría que un reintento con saldo ya distinto NUNCA chocara
contra la liquidación original — el mismo evento se facturaría dos veces. Por eso `uq_bcm_liquidacion`
va sobre (`id_suministrador`, `codigo_articulo`, `tipo`, `id_documento`): `id_suministrador` SÍ es
estable para el mismo evento de consumo (es un dato del lote consumido, no del reparto), así que el
reclamo funciona igual sin importar qué depósito(s) concretos lo financiaron. Mismo principio exacto
que `rappel_liquidaciones.uq_rl_ventana` (`0258_b2b_rappels.py`) — el INSERT amparado por la UNIQUE KEY
ES el reclamo atómico de "exactamente una vez" — pero anclado a la identidad correcta del evento.

`tipo` forma parte de la clave porque esta tabla comparte fila para los cuatro tipos de evento: sin
`tipo`, una fila CONSUMO del mismo (suministrador, artículo) con el mismo `id_documento` que su fila
LIQUIDACION hermana (mismo evento, deliberadamente el mismo `id_documento` para trazabilidad)
chocaría contra ella. Con `tipo` en la clave, sólo se bloquea lo que se pretende bloquear: dos
LIQUIDACION para el mismo evento. `registrar_consumo_consignacion` reserva `id_documento=NULL` en
las filas DEPOSITO/CONSUMO (varios NULL conviven sin chocar en una UNIQUE KEY de MariaDB) — sólo la
fila LIQUIDACION lleva el `id_documento` real y es, por tanto, la única sujeta al reclamo.
"""

VERSION = "0269"
DESCRIPCION = "Stock en Consignación: es_consignacion en transaccion_comercial + b2b_consignacion_saldo/movimientos"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA_TX = "transaccion_comercial"
_COL_TX = [("es_consignacion", "TINYINT(1) NOT NULL DEFAULT 0")]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _COL_TX:
        if not _existe_columna(cur, _TABLA_TX, col):
            cur.execute(f"ALTER TABLE {_TABLA_TX} ADD COLUMN {col} {ddl}")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS b2b_consignacion_saldo (
            id_tx                CHAR(36) NOT NULL,
            codigo_articulo      VARCHAR(64) NOT NULL,
            id_suministrador     BIGINT NOT NULL,
            id_empresa           CHAR(36) NOT NULL,
            cantidad_depositada  INT NOT NULL DEFAULT 0,
            cantidad_consumida   INT NOT NULL DEFAULT 0,
            cantidad_devuelta    INT NOT NULL DEFAULT 0,
            precio_unitario      DECIMAL(12,4) NOT NULL DEFAULT 0,
            actualizado          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id_tx, codigo_articulo),
            INDEX idx_bcs_suministrador (id_suministrador),
            INDEX idx_bcs_empresa (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS b2b_consignacion_movimientos (
            id               BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_tx            CHAR(36) NOT NULL,
            id_suministrador BIGINT NOT NULL,
            codigo_articulo  VARCHAR(64) NOT NULL,
            tipo             VARCHAR(20) NOT NULL,
            cantidad         INT NOT NULL,
            id_documento     VARCHAR(80) DEFAULT NULL,
            creado           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_bcm_tx (id_tx),
            INDEX idx_bcm_suministrador (id_suministrador),
            UNIQUE KEY uq_bcm_liquidacion (id_suministrador, codigo_articulo, tipo, id_documento)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS b2b_consignacion_movimientos")
    cur.execute("DROP TABLE IF EXISTS b2b_consignacion_saldo")
    for col, _ in reversed(_COL_TX):
        if _existe_columna(cur, _TABLA_TX, col):
            cur.execute(f"ALTER TABLE {_TABLA_TX} DROP COLUMN {col}")
