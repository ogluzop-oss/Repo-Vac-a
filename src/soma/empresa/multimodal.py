"""
Respuestas MULTIMODALES (Fase 8). Amplía las visualizaciones de SOMA (gráficos sencillos, comparativas,
líneas temporales, evolución mensual, tendencias) SIN abrir ventanas nuevas y SIN tocar el overlay:
produce dicts `visual` en los tipos que el panel conversacional YA sabe renderizar con componentes
Enterprise (`tabla`, `kpis`, `timeline`, `lista`). Un gráfico sencillo se representa como sparkline
Unicode dentro del texto + una línea temporal Enterprise.
"""

_BLOQUES = "▁▂▃▄▅▆▇█"


def sparkline(valores) -> str:
    """Mini-gráfico de tendencia en texto (sin dependencias, no abre ventanas)."""
    vals = [float(v or 0) for v in (valores or [])]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return _BLOQUES[3] * len(vals)
    return "".join(_BLOQUES[min(len(_BLOQUES) - 1, int((v - lo) / (hi - lo) * (len(_BLOQUES) - 1)))]
                   for v in vals)


def evolucion(titulo, serie) -> dict:
    """Evolución mensual / línea temporal → visual 'timeline' (Enterprise). serie = [{fecha, valor}]."""
    items = []
    prev = None
    for p in (serie or [])[-12:]:
        val = float(p.get("valor") or 0)
        rol = "ok" if (prev is None or val >= prev) else "advertencia"
        items.append({"texto": f"{titulo}: {round(val, 2)}", "fecha": str(p.get("fecha", "")), "rol": rol})
        prev = val
    return {"tipo": "timeline", "items": items}


def comparativa(filas) -> dict:
    """Comparativa antes/ahora → visual 'tabla'. filas = [{concepto, antes, ahora, variacion}]."""
    return {"tipo": "tabla", "columnas": ["Concepto", "Antes", "Ahora", "Variación"],
            "filas": [{"Concepto": f.get("concepto", ""), "Antes": f.get("antes", ""),
                       "Ahora": f.get("ahora", ""), "Variación": f.get("variacion", "")}
                      for f in (filas or [])]}


def tendencia(titulo, serie) -> dict:
    """Tendencia resumida → visual 'kpis' con color por dirección + sparkline en el título."""
    vals = [float(p.get("valor") or 0) for p in (serie or [])]
    if not vals:
        return {"tipo": "kpis", "items": []}
    direccion = "sube" if vals[-1] >= vals[0] else "baja"
    riesgo = "BAJO" if direccion == "sube" else "MEDIO"
    spark = sparkline(vals)
    return {"tipo": "kpis", "items": [
        {"titulo": f"{titulo} {spark}", "valor": f"{round(vals[-1], 2)} ({direccion})", "riesgo": riesgo}]}
