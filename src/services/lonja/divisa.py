"""Conversión de divisas del mercado (Lonja).

`lonja_tipos_cambio` guarda `tasa_eur` = cuántos EUR vale 1 unidad de la divisa. La conversión entre dos
divisas pasa por EUR. Si una divisa no tiene tasa, se asume 1.0 (conversión aproximada; el importe original
SIEMPRE se conserva aparte, así que no se falsea el dato de origen).
"""

from ._common import _conn, _filas, logger


def set_tasa(divisa, tasa_eur) -> bool:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO lonja_tipos_cambio (divisa, tasa_eur) VALUES (%s,%s) "
                        "ON DUPLICATE KEY UPDATE tasa_eur=VALUES(tasa_eur), actualizado=NOW()",
                        (str(divisa).upper()[:8], float(tasa_eur)))
            c.commit()
        return True
    except Exception as e:
        logger.error("set_tasa: %s", e)
        return False


def tasa(divisa) -> float:
    """EUR por 1 unidad de `divisa` (1.0 para EUR o si se desconoce)."""
    d = str(divisa or "EUR").upper()
    if d == "EUR":
        return 1.0
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT tasa_eur FROM lonja_tipos_cambio WHERE divisa=%s", (d,))
            r = cur.fetchone()
        if not r:
            return 1.0
        v = r[0] if not isinstance(r, dict) else list(r.values())[0]
        return float(v or 1.0)
    except Exception as e:
        logger.debug("tasa(%s): %s", d, e)
        return 1.0


def convertir(monto, de, a="EUR") -> float:
    """Convierte `monto` de la divisa `de` a la divisa `a` vía EUR."""
    try:
        m = float(monto or 0)
    except (TypeError, ValueError):
        return 0.0
    ta, tb = tasa(de), tasa(a)
    if not tb:
        return m
    return round(m * ta / tb, 4)


def tasas() -> list:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT divisa, tasa_eur, actualizado FROM lonja_tipos_cambio ORDER BY divisa")
            return _filas(cur)
    except Exception as e:
        logger.error("tasas: %s", e)
        return []
