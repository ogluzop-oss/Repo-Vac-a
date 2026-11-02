"""
Migración 0289 — Motor de descuentos y promociones (e-commerce, Fase 2 de Catálogo Web):
condiciones reales de cupón (fecha de inicio, límite de usos TOTALES configurable, importe
mínimo de carrito) + tipo "envío gratis". ADITIVA, reversible, idempotente.

Antes de esto, `cupones` ya existía (migración 0037) pero era de usar-y-tirar: una redención
cualquiera marcaba el cupón entero como 'usado' para siempre (sin contador), sin fecha de inicio
(solo caducidad) y sin importe mínimo de pedido — huecos reales que pedía el encargo
("fechas de validez, límite de usos totales y uso mínimo por cliente").

`uso_maximo` por DEFECTO vale 1 (no NULL): preserva EXACTAMENTE el comportamiento actual de
cualquier cupón ya creado (un solo uso) — el multi-uso es opt-in, nunca retroactivo por omisión.
"""

VERSION = "0289"
DESCRIPCION = "Cupones: fecha de inicio, límite de usos configurable, importe mínimo"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
        "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n) > 0


def _add_col(cur, tabla, columna, definicion):
    if not _existe_columna(cur, tabla, columna):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def aplicar(cur):
    _add_col(cur, "cupones", "fecha_inicio", "DATE DEFAULT NULL")
    _add_col(cur, "cupones", "uso_maximo", "INT NOT NULL DEFAULT 1")
    _add_col(cur, "cupones", "usos_actuales", "INT NOT NULL DEFAULT 0")
    _add_col(cur, "cupones", "importe_minimo", "DECIMAL(10,2) DEFAULT NULL")


def revertir(cur):
    for col in ("fecha_inicio", "uso_maximo", "usos_actuales", "importe_minimo"):
        if _existe_columna(cur, "cupones", col):
            cur.execute(f"ALTER TABLE cupones DROP COLUMN {col}")
