"""
Risk Engine (Fase 7). Detecta RIESGOS empresariales estructurados (nivel, probabilidad, impacto,
causas, consecuencias, acciones sugeridas, especialistas). REUTILIZA el motor de razonamiento de la
Fase 4 (`razonamiento`) — que ya interpreta PredictionService/Gemelo/Workflow/Auditoría/KPIs — y lo
enriquece; no crea un segundo detector.
"""

from src.soma import prioridad as P
from src.soma import razonamiento

_ESPECIALISTA = {"inventario": "Inventario", "stock": "Inventario", "tesoreria": "Tesorería",
                 "financiero": "Tesorería", "workflow": "Workflow", "auditoria": "Auditoría",
                 "riesgo": "Predicción", "comercial": "Comercial", "empresa": "Gemelo Digital",
                 "fiscal": "Fiscal", "compras": "Compras", "rrhh": "RRHH"}

_PROB = {P.CRITICA: "alta", P.ALTA: "alta", P.MEDIA: "media", P.BAJA: "baja", P.MUY_BAJA: "baja"}
_IMPACTO = {P.CRITICA: "muy alto", P.ALTA: "alto", P.MEDIA: "medio", P.BAJA: "bajo", P.MUY_BAJA: "bajo"}


def detectar(id_empresa=None) -> list:
    """Devuelve la lista de riesgos estructurados a partir de los hallazgos del razonamiento."""
    riesgos = []
    for h in razonamiento.recopilar(id_empresa):
        prio = h.get("prioridad", P.MEDIA)
        riesgos.append({
            "clave": "riesgo_" + h.get("clave", ""),
            "tipo": "riesgo",
            "titulo": h.get("titulo", "Riesgo"),
            "dominio": h.get("dominio", "general"),
            "nivel": prio,
            "prioridad": prio,
            "probabilidad": _PROB.get(prio, "media"),
            "impacto": _IMPACTO.get(prio, "medio"),
            "causas": h.get("por_que", ""),
            "consecuencias": h.get("consecuencias", ""),
            "acciones": h.get("accion", ""),
            "especialistas": [_ESPECIALISTA.get(h.get("dominio"), "Predicción")],
            "mensaje": h.get("mensaje", h.get("titulo", "")),
            "por_que": h.get("por_que", ""),
            "datos": h.get("datos", {}),
        })
    return riesgos
