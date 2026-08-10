"""
Generador de INICIATIVAS (Fase 7). Combina riesgos + oportunidades + objetivos en una lista de
iniciativas priorizadas y EXPLICABLES (por_que / datos / especialistas / consecuencias / qué pasa si
no hago nada), y aplica el APRENDIZAJE lento de prioridades según decisiones previas del usuario. Cada
iniciativa puede llevar una MISIÓN propuesta (Mission Engine). No ejecuta nada: solo propone.
"""

import logging

from src.soma import prioridad as P
from src.soma.direccion import historial, objetivos, oportunidades, riesgos

logger = logging.getLogger("soma.direccion.iniciativas")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def generar(id_empresa=None, *, usuario=None) -> list:
    emp = _emp(id_empresa)
    rs = riesgos.detectar(emp)
    op = oportunidades.detectar(emp)
    ob = objetivos.generar(rs, op, emp)
    todas = list(rs) + list(op) + list(ob)

    # Aprendizaje lento: ajusta la prioridad efectiva por tipo según aceptaciones/rechazos previos.
    for i in todas:
        try:
            delta = historial.ajuste_prioridad(i.get("tipo", "riesgo"), usuario=usuario, id_empresa=emp)
            if delta:
                i["prioridad"] = historial.aplicar_ajuste(i.get("prioridad", P.MEDIA), delta)
        except Exception:
            pass
        # Explicabilidad total (incluye "qué pasa si no hago nada").
        i.setdefault("si_no_hago_nada",
                     i.get("consecuencias") or "La situación podría mantenerse o agravarse con el tiempo.")
        i.setdefault("especialistas", [])
        i.setdefault("acciones", "")

    # Dedup por clave y orden por prioridad.
    vistos, unicas = set(), []
    for i in todas:
        k = i.get("clave")
        if k and k not in vistos:
            vistos.add(k)
            unicas.append(i)
    unicas.sort(key=lambda i: P.nivel(i.get("prioridad")), reverse=True)
    return unicas


def explicar(ini) -> str:
    """Explicabilidad total de una iniciativa."""
    if not isinstance(ini, dict):
        return "No tengo el detalle de esa recomendación."
    partes = []
    if ini.get("por_que"):
        partes.append(f"Te lo recomiendo porque {ini['por_que']}")
    if ini.get("datos"):
        d = ", ".join(f"{k}: {v}" for k, v in (ini.get("datos") or {}).items())
        if d:
            partes.append(f"Me baso en estos datos: {d}.")
    if ini.get("especialistas"):
        partes.append("Especialistas consultados: " + ", ".join(ini["especialistas"]) + ".")
    if ini.get("consecuencias"):
        partes.append(f"Consecuencias: {ini['consecuencias']}")
    if ini.get("si_no_hago_nada"):
        partes.append(f"Si no hacemos nada: {ini['si_no_hago_nada']}")
    return " ".join(partes) or "Te lo comento a partir de la información viva del ERP."
