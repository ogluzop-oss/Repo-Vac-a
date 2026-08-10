"""
Contexto TEMPORAL de SOMA (Fase 7). Comprende el momento (inicio/mediodía/tarde/cierre del día, fin de
semana, periodo fiscal, campañas, rebajas, navidad, inventario) para adaptar las recomendaciones. Sin
dependencias externas: derivado de la fecha/hora y de marcadores del negocio.
"""

import datetime


def momento(ahora=None) -> dict:
    now = ahora or datetime.datetime.now()
    h = now.hour
    franja = ("inicio" if h < 10 else "mediodia" if h < 14 else "tarde" if h < 19 else "cierre")
    dia = now.weekday()          # 0=lunes … 6=domingo
    fin_semana = dia >= 5
    mes, d = now.month, now.day
    if mes == 12:
        periodo = "navidad"
    elif mes in (1, 7) and d <= 20:
        periodo = "rebajas"
    elif mes in (1, 4, 7, 10) and d <= 20:
        periodo = "fiscal"       # cercanía de presentación trimestral
    else:
        periodo = "normal"
    return {"franja": franja, "hora": h, "dia_semana": dia, "fin_semana": fin_semana,
            "periodo": periodo, "fecha": now.strftime("%Y-%m-%d")}


def saludo(m=None) -> str:
    m = m or momento()
    base = {"inicio": "Buenos días", "mediodia": "Buenas", "tarde": "Buenas tardes",
            "cierre": "Antes de cerrar"}.get(m["franja"], "Hola")
    return base


def matiz(m=None) -> str:
    """Un matiz breve según el momento (para dar naturalidad a las recomendaciones)."""
    m = m or momento()
    if m["franja"] == "cierre":
        return "Ya que se acerca el cierre, "
    if m["periodo"] == "navidad":
        return "En plena campaña de navidad, "
    if m["periodo"] == "rebajas":
        return "En periodo de rebajas, "
    if m["periodo"] == "fiscal":
        return "Con el cierre fiscal cerca, "
    if m["fin_semana"]:
        return "Aunque es fin de semana, "
    return ""
