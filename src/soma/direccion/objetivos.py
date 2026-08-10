"""
Autonomous Goal Engine (Fase 7). Genera OBJETIVOS empresariales sin intervención del usuario, siempre
RAZONADOS a partir de los riesgos y oportunidades detectados (nunca reglas aisladas). Cada objetivo se
vincula, cuando procede, a una plantilla de MISIÓN existente (Mission Engine) para poder ofrecer un
plan. No ejecuta nada.
"""

from src.soma import prioridad as P

# Grupos de dominio → (clave objetivo, título, misión sugerida)
_GRUPOS = [
    (("stock", "inventario"), "optimizar_inventario", "Optimizar el inventario y las compras",
     "reducir_costes"),
    (("compras",), "optimizar_compras", "Optimizar las compras", "reducir_costes"),
    (("tesoreria", "financiero"), "proteger_liquidez", "Proteger la liquidez y reducir impagos",
     "reducir_costes"),
    (("comercial", "ventas", "crm"), "incrementar_ventas", "Incrementar las ventas", "mejorar_ventas"),
    (("workflow",), "agilizar_procesos", "Agilizar los procesos pendientes", None),
    (("auditoria",), "reforzar_control", "Reforzar el control interno", None),
]


def _objetivo(clave, titulo, prioridad, dominio, *, mision=None, por_que="", especialistas=None):
    return {"clave": "obj_" + clave, "tipo": "objetivo", "titulo": titulo,
            "mensaje": f"Creo que sería conveniente marcarnos un objetivo: {titulo.lower()}.",
            "prioridad": prioridad, "dominio": dominio, "por_que": por_que, "datos": {},
            "consecuencias": "", "especialistas": especialistas or ["Gemelo Digital", "Predicción"],
            "acciones": "", "mision": mision}


def generar(riesgos, oportunidades, id_empresa=None) -> list:
    """Deriva objetivos de negocio a partir de la ACUMULACIÓN de señales (riesgos + oportunidades)."""
    señales = list(riesgos or []) + list(oportunidades or [])
    if not señales:
        return []
    # Agrupar por dominio y quedarse con la peor prioridad de cada grupo.
    peor_por_dom = {}
    for s in señales:
        dom = s.get("dominio", "general")
        peor_por_dom[dom] = P.peor(peor_por_dom.get(dom, P.MUY_BAJA), s.get("prioridad", P.MEDIA))
    objetivos = []
    usados = set()
    for doms, clave, titulo, mision in _GRUPOS:
        prio = P.MUY_BAJA
        cuenta = 0
        for d in doms:
            if d in peor_por_dom:
                prio = P.peor(prio, peor_por_dom[d])
                cuenta += 1
        if cuenta and clave not in usados:
            usados.add(clave)
            objetivos.append(_objetivo(
                clave, titulo, prio, doms[0], mision=mision,
                por_que=("Lo propongo porque varias señales (riesgos/oportunidades) apuntan a "
                         f"«{titulo.lower()}»."),
                especialistas=["Gemelo Digital", "Predicción"]))
    return objetivos
