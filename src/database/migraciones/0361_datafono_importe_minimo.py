"""
Migración 0361 — Importe mínimo para aceptar pagos con tarjeta en el TPV (petición explícita,
2026-11-23). Columna nueva en `tpv_datafono_config` (configuración del datáfono físico, una fila
por tienda — ver `db/datafono.py`): mismo criterio que `descuento_min_bloqueo` en
`db/config_ticket.py` (umbral `DECIMAL` NULO = sin mínimo, no bloquea nada).
"""

VERSION = "0361"
DESCRIPCION = "Columna importe_minimo_tarjeta en tpv_datafono_config"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() "
        "AND table_name=%s AND column_name=%s", (tabla, columna))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "tpv_datafono_config", "importe_minimo_tarjeta"):
        cur.execute("ALTER TABLE tpv_datafono_config ADD COLUMN importe_minimo_tarjeta "
                   "DECIMAL(10,2) DEFAULT NULL")


def revertir(cur):
    if _tiene_columna(cur, "tpv_datafono_config", "importe_minimo_tarjeta"):
        cur.execute("ALTER TABLE tpv_datafono_config DROP COLUMN importe_minimo_tarjeta")
