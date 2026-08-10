"""
Calendario del Enterprise Scheduler (Fase III · B3) — cálculo de la próxima ejecución.

Tipos: inmediata/diferida/diaria/semanal/mensual/trimestral/anual/cron. `cron` usa `croniter` si está
disponible (degradable). Sin dependencias duras nuevas.
"""

import datetime as _dt


def _suma_meses(base, meses):
    m = base.month - 1 + meses
    y = base.year + m // 12
    m = m % 12 + 1
    import calendar
    d = min(base.day, calendar.monthrange(y, m)[1])
    return base.replace(year=y, month=m, day=d)


def proxima(tipo, expresion=None, *, base=None) -> _dt.datetime | None:
    """Devuelve la próxima ejecución (datetime) o None si es puntual ya vencida/desconocida."""
    base = base or _dt.datetime.now()
    tipo = (tipo or "cron").lower()
    if tipo == "inmediata":
        return base
    if tipo == "diferida":
        try:
            return _dt.datetime.fromisoformat(expresion) if expresion else base
        except Exception:
            return base
    if tipo == "diaria":
        return base + _dt.timedelta(days=1)
    if tipo == "semanal":
        return base + _dt.timedelta(weeks=1)
    if tipo == "mensual":
        return _suma_meses(base, 1)
    if tipo == "trimestral":
        return _suma_meses(base, 3)
    if tipo == "anual":
        return _suma_meses(base, 12)
    if tipo == "cron":
        try:
            from croniter import croniter
            return croniter(expresion, base).get_next(_dt.datetime)
        except Exception:
            return None   # degradable: sin croniter, no se auto-programa el cron
    return None
