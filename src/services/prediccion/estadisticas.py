"""
Utilidades estadisticas puras para el motor predictivo (Paquete Enterprise 3). Sin estado, sin
dependencias del ERP. Base de heuristicas y tendencias.
"""

import statistics


def media(v) -> float:
    return float(statistics.mean(v)) if v else 0.0


def desviacion(v) -> float:
    return float(statistics.pstdev(v)) if len(v) > 1 else 0.0


def media_movil(v, n=7) -> float:
    return media(v[-n:]) if v else 0.0


def tendencia_lineal(v) -> float:
    """Pendiente por minimos cuadrados sobre el indice temporal."""
    n = len(v)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = media(xs), media(v)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, v))
    den = sum((x - mx) ** 2 for x in xs)
    return (num / den) if den else 0.0


def variacion_pct(actual, previo) -> float:
    if not previo:
        return 0.0
    return round((actual - previo) / previo * 100.0, 2)


def z_score(x, v) -> float:
    d = desviacion(v)
    return round((x - media(v)) / d, 2) if d else 0.0


def proyeccion(v, pasos=1) -> float:
    """Proyeccion lineal a `pasos` (nunca negativa)."""
    if not v:
        return 0.0
    return max(0.0, v[-1] + tendencia_lineal(v) * pasos)


def confianza(v) -> float:
    """Confianza 0..1 en funcion del volumen y estabilidad de la serie."""
    if not v:
        return 0.2
    m = media(v)
    vol = (desviacion(v) / m) if m else 1.0
    base = min(len(v) / 30.0, 1.0)          # mas historico → mas confianza
    return round(max(0.2, min(0.9, base * (1.0 - min(vol, 0.8)))), 2)
