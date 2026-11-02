"""
Migración 0268 — Landed Cost (Fase B): método de reparto en `compras_costes_extra` + desglose
auditable por componente en la nueva tabla `compras_costes_extra_lineas`. ADITIVA, reversible.

`metodo_prorrateo` (valor|cantidad|peso, VARCHAR libre + validación en Python — mismo idioma que
el resto de "enums" de este código base, p. ej. `compras_incidencias.tipo`) decide cómo
`db.compras.prorratear_costes_recepcion()` reparte cada componente de coste indirecto entre las
líneas recibidas; por defecto 'cantidad' (comportamiento histórico: reparto a partes iguales por
unidad). `id_tx` (nullable) permite registrar costes extra sobre un pedido B2B ya recibido
(`transaccion_comercial`), alternativa a `id_recepcion`/`id_pedido` — Smart Suppliers no genera
fila en `compras_recepciones`.

`compras_costes_extra_lineas`: una fila por (componente de coste indirecto × línea recibida) — el
desglose auditable completo que pide Landed Cost. Aditiva/append-only por diseño: nunca se
sobreescribe ni se borra, así reejecutar el prorrateo tras registrar un componente nuevo conserva
el histórico completo. `id_recepcion`/`id_recepcion_linea` son NULL en las filas B2B (que se
identifican solo por `id_coste_extra` → `compras_costes_extra.id_tx`, sin duplicar la columna
aquí). Mismo idioma de migración que `0266_lotes_coste_landed.py` (guard `_existe_columna`,
`aplicar`/`revertir`).
"""

VERSION = "0268"
DESCRIPCION = "Landed Cost: metodo_prorrateo/id_tx en compras_costes_extra + compras_costes_extra_lineas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS_CCE = [
    ("metodo_prorrateo", "VARCHAR(20) NOT NULL DEFAULT 'cantidad'"),
    ("id_tx", "CHAR(36) DEFAULT NULL"),
]


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _COLS_CCE:
        if not _existe_columna(cur, "compras_costes_extra", col):
            cur.execute(f"ALTER TABLE compras_costes_extra ADD COLUMN {col} {ddl}")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compras_costes_extra_lineas (
            id                        BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa                CHAR(36) NOT NULL,
            id_recepcion              BIGINT DEFAULT NULL,
            id_recepcion_linea        BIGINT DEFAULT NULL,
            codigo_articulo           VARCHAR(64) NOT NULL,
            cantidad                  INT NOT NULL,
            coste_base_unitario       DECIMAL(12,4) NOT NULL DEFAULT 0,
            id_coste_extra            BIGINT NOT NULL,
            tipo_coste_extra          VARCHAR(20) NOT NULL,
            importe_asignado          DECIMAL(12,4) NOT NULL DEFAULT 0,
            coste_unitario_indirecto  DECIMAL(12,4) NOT NULL DEFAULT 0,
            coste_unitario_landed     DECIMAL(12,4) NOT NULL DEFAULT 0,
            metodo_usado              VARCHAR(20) NOT NULL,
            fecha                     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_cel_recepcion (id_recepcion),
            INDEX idx_cel_coste_extra (id_coste_extra)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS compras_costes_extra_lineas")
    for col, _ in reversed(_COLS_CCE):
        if _existe_columna(cur, "compras_costes_extra", col):
            cur.execute(f"ALTER TABLE compras_costes_extra DROP COLUMN {col}")
