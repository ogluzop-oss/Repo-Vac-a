"""
Analisis e interpretacion de KPIs (SUBFASE 9). La IA no sustituye los graficos de BI: los
INTERPRETA (explica, compara, concluye). Solo lectura sobre el panel de BI existente.
"""

from src.services.ia import adaptadores as A
from src.services.ia import configuracion as C
from src.services.ia.modelos import Insight


def interpretar_kpis(id_empresa=None, *, periodo="mes") -> list:
    if not C.activo("analisis", id_empresa):
        return []
    panel = A.kpis(id_empresa, periodo=periodo)
    secc = panel.get("secciones") or {}
    ins = []
    for dom, items in secc.items():
        for it in (items or []):
            nombre = str(it.get("nombre") or "").lower()
            try:
                v = float(it.get("valor"))
            except (TypeError, ValueError):
                continue
            etq = it.get("nombre")
            if "rotura" in nombre and v > 0:
                ins.append(Insight("bi", f"{etq}: {v:.0f}",
                                   "Hay roturas de stock; conviene revisar la reposicion.", "critico", it))
            elif "merma" in nombre and v > 0:
                ins.append(Insight("bi", f"{etq}: {v:.0f}", "Merma detectada en el periodo.", "aviso", it))
            elif "margen" in nombre:
                ins.append(Insight("bi", f"{etq}: {v:.2f}",
                                   "Margen positivo." if v >= 0 else "Margen negativo: revisar costes/precios.",
                                   "ok" if v >= 0 else "critico", it))
            elif "facturaci" in nombre or "ticket" in nombre or "ventas" in nombre:
                ins.append(Insight("bi", f"{etq}: {v:.2f}", "", "info", it))
    if not ins:
        ins.append(Insight("bi", "Sin desviaciones notables en los KPIs del periodo", "", "ok"))
    return ins[:12]
