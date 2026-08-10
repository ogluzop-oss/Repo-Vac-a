"""
Comparador de escenarios (Paquete Enterprise 9, SUBFASE 9.13). Compara el estado actual (base) con
uno o varios escenarios simulados y muestra diferencias por metrica. Solo lectura sobre escenarios
virtuales.
"""

import logging

from src.services.simulador import base as B
from src.services.simulador import modelo as M

logger = logging.getLogger("simulador.comparador")


def _delta(base, sim):
    d = round(sim - base, 2)
    dp = round((d / base * 100), 2) if base else (100.0 if sim else 0.0)
    return d, dp


def comparar(id_empresa, resultados_por_escenario) -> dict:
    """resultados_por_escenario: [{'id':..,'nombre':..,'metricas':{...}}]. El primero es el base
    si se indica; si no, se toma el estado actual del Gemelo Digital como base."""
    base_m = B.metricas_base(id_empresa)
    columnas = [{"id": None, "nombre": "Actual", "metricas": base_m}] + list(resultados_por_escenario)

    filas = []
    for met in M.METRICAS:
        fila = {"metrica": met, "actual": round(float(base_m.get(met, 0) or 0), 2), "escenarios": []}
        for col in resultados_por_escenario:
            v = round(float(col["metricas"].get(met, 0) or 0), 2)
            d, dp = _delta(fila["actual"], v)
            fila["escenarios"].append({"id": col.get("id"), "nombre": col.get("nombre"),
                                       "valor": v, "delta": d, "delta_pct": dp})
        filas.append(fila)

    return {"id_empresa": id_empresa, "columnas": [c["nombre"] for c in columnas], "filas": filas}
