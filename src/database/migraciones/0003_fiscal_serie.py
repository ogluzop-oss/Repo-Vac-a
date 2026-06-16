"""
Migración 0003 — Estrategia de serie fiscal configurable (C3.2).

Añade `serie_por` a `fiscal_config`: define el ÁMBITO de la numeración/cadena hash
de los registros fiscales (cada serie efectiva tiene su propia cadena):

    'empresa' → una única serie por empresa.
    'tienda'  → una serie por tienda (POR DEFECTO).
    'caja'    → una serie por caja/terminal.

Aditiva e idempotente (se comprueba la existencia de la columna). Reversible.
No contiene secretos ni altera datos existentes (los registros ya emitidos
conservan su serie textual; el cambio solo afecta a cómo se resuelve la serie
de los NUEVOS registros).
"""

VERSION = "0003"
DESCRIPCION = "Estrategia de serie fiscal configurable (serie_por: empresa/tienda/caja)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (tabla, columna))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n or 0) > 0


def aplicar(cur):
    # fiscal_config debe existir (la crea 0002). Si no existiera, no hacemos nada:
    # 0002 ya la crea con su esquema base y esta migración es puramente aditiva.
    if not _tiene_columna(cur, "fiscal_config", "serie_por"):
        cur.execute(
            "ALTER TABLE fiscal_config "
            "ADD COLUMN serie_por VARCHAR(10) NOT NULL DEFAULT 'tienda' AFTER serie")


def revertir(cur):
    if _tiene_columna(cur, "fiscal_config", "serie_por"):
        cur.execute("ALTER TABLE fiscal_config DROP COLUMN serie_por")
