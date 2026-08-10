"""
Deteccion e interpretacion de tendencias (Paquete Enterprise 3, SUBFASE 3.9). No solo grafica:
interpreta (subida/bajada/estable, volatilidad, estacionalidad semanal).
"""

from src.services.prediccion import estadisticas as E


def analizar(valores) -> dict:
    if not valores:
        return {"tendencia": "sin_datos", "pendiente": 0.0, "variacion_pct": 0.0,
                "volatilidad": 0.0, "media": 0.0}
    sl = E.tendencia_lineal(valores)
    m = E.media(valores)
    tercio = max(1, len(valores) // 3)
    var = E.variacion_pct(E.media(valores[-tercio:]), E.media(valores[:tercio]))
    vol = round(E.desviacion(valores) / m, 2) if m else 0.0
    if sl > m * 0.02:
        t = "subida"
    elif sl < -m * 0.02:
        t = "bajada"
    else:
        t = "estable"
    return {"tendencia": t, "pendiente": round(sl, 3), "variacion_pct": var,
            "volatilidad": vol, "media": round(m, 2)}


def estacionalidad_semanal(pares_dia_valor) -> dict:
    """Media por dia de la semana (0=lunes) a partir de [(weekday, valor), ...]."""
    acum, cnt = {}, {}
    for wd, val in pares_dia_valor:
        acum[wd] = acum.get(wd, 0.0) + float(val or 0)
        cnt[wd] = cnt.get(wd, 0) + 1
    return {wd: round(acum[wd] / cnt[wd], 2) for wd in acum}


def interpretar(analisis: dict) -> str:
    t = analisis.get("tendencia")
    var = analisis.get("variacion_pct", 0)
    if t == "subida":
        return f"Tendencia al alza (+{abs(var):.0f}%)."
    if t == "bajada":
        return f"Tendencia a la baja (-{abs(var):.0f}%)."
    if t == "sin_datos":
        return "Sin datos suficientes."
    return "Comportamiento estable."
