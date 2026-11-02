"""
Fase Productividad · Cálculo de límites de periodo (calendario), SIN cron de "cierre".

Diseño deliberado (igual criterio que el resto de la app: degradación honesta, nunca un motor
paralelo): no existe ningún job en segundo plano que "cierre" un periodo. Cada barra de progreso
se recalcula EN VIVO llamando a `limites_periodo(tipo, fecha_ref=hoy)` — en cuanto `hoy` cruza al
periodo siguiente, el cálculo cambia solo, sin que nada tenga que resetear nada a mano. La
navegación histórica (`navegar`) se acota al año natural en curso (nunca antes del 1 de enero de
este año) y nunca al futuro.
"""

import calendar
from datetime import date, timedelta

TIPOS = ("diario", "semanal", "bimensual", "mensual", "bimestral", "trimestral", "semestral", "anual")

# Únicos 3 obligatorios al configurar objetivos (el resto son opcionales) — pedido explícito.
OBLIGATORIOS = ("mensual", "semestral", "anual")


def _lunes_de_semana_iso(iso_year: int, iso_week: int) -> date:
    try:
        return date.fromisocalendar(iso_year, iso_week, 1)
    except ValueError:
        # Semana fuera de rango (el año ISO no tiene esa semana, p.ej. pedir la 53 en un año de 52)
        # → la última semana válida de ese año ISO, nunca una excepción sin capturar.
        return date.fromisocalendar(iso_year, 52, 1)


def limites_periodo(tipo: str, fecha_ref: date | None = None) -> tuple[date, date]:
    """(desde, hasta) — ambas inclusive — del periodo `tipo` que contiene `fecha_ref` (hoy si se
    omite). Todos los periodos son ALINEADOS AL CALENDARIO (no "últimos N días" relativos)."""
    f = fecha_ref or date.today()
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de periodo desconocido: {tipo!r}")

    if tipo == "diario":
        return f, f

    if tipo == "semanal":
        desde = f - timedelta(days=f.weekday())
        return desde, desde + timedelta(days=6)

    if tipo == "bimensual":
        iso_year, iso_week, _ = f.isocalendar()
        semana_par_inicio = iso_week if iso_week % 2 == 1 else iso_week - 1
        desde = _lunes_de_semana_iso(iso_year, semana_par_inicio)
        return desde, desde + timedelta(days=13)

    if tipo == "mensual":
        desde = f.replace(day=1)
        ultimo = calendar.monthrange(f.year, f.month)[1]
        return desde, f.replace(day=ultimo)

    if tipo == "bimestral":
        mes_inicio = ((f.month - 1) // 2) * 2 + 1
        mes_fin = mes_inicio + 1
        desde = date(f.year, mes_inicio, 1)
        ultimo = calendar.monthrange(f.year, mes_fin)[1]
        return desde, date(f.year, mes_fin, ultimo)

    if tipo == "trimestral":
        mes_inicio = ((f.month - 1) // 3) * 3 + 1
        mes_fin = mes_inicio + 2
        desde = date(f.year, mes_inicio, 1)
        ultimo = calendar.monthrange(f.year, mes_fin)[1]
        return desde, date(f.year, mes_fin, ultimo)

    if tipo == "semestral":
        if f.month <= 6:
            return date(f.year, 1, 1), date(f.year, 6, 30)
        return date(f.year, 7, 1), date(f.year, 12, 31)

    # anual
    return date(f.year, 1, 1), date(f.year, 12, 31)


def limite_minimo_navegacion() -> date:
    """1 de enero del año natural EN CURSO — las barras históricas no se muestran más allá
    (pedido explícito: una vez cierra el año natural, esos resultados dejan de mostrarse)."""
    return date(date.today().year, 1, 1)


def navegar(tipo: str, fecha_cursor: date, direccion: str) -> date | None:
    """Mueve el cursor un periodo hacia "atras" o "adelante". Devuelve una fecha DENTRO del nuevo
    periodo (para volver a pasarla a `limites_periodo`), o `None` si el movimiento está bloqueado
    (atrás: cruzaría al año natural anterior; adelante: entraría en el futuro)."""
    desde, hasta = limites_periodo(tipo, fecha_cursor)
    if direccion == "atras":
        candidata = desde - timedelta(days=1)
        if candidata < limite_minimo_navegacion():
            return None
        return candidata
    if direccion == "adelante":
        candidata = hasta + timedelta(days=1)
        if candidata > date.today():
            return None
        return candidata
    raise ValueError(f"Dirección desconocida: {direccion!r}")
