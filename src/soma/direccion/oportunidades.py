"""
Opportunity Engine (Fase 7). No solo detecta problemas: también OPORTUNIDADES (clientes que podrían
volver, productos con crecimiento, sobrestock a liquidar con ventaja, proveedores a revisar, campañas
recomendables por temporada…). Reutiliza PredictionService/Gemelo/BD e integra el contexto temporal.
Cada oportunidad se prioriza. Best-effort: si una fuente no está, se omite sin romper.
"""

import logging

from src.soma import prioridad as P
from src.soma.direccion import temporal

logger = logging.getLogger("soma.direccion.oportunidades")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def _opp(clave, titulo, mensaje, *, prioridad=P.MEDIA, dominio="comercial", por_que="",
         datos=None, consecuencias="", especialistas=None, mision=None):
    return {"clave": "opp_" + clave, "tipo": "oportunidad", "titulo": titulo, "mensaje": mensaje,
            "prioridad": prioridad, "dominio": dominio, "por_que": por_que, "datos": datos or {},
            "consecuencias": consecuencias, "especialistas": especialistas or ["Predicción"],
            "acciones": "", "mision": mision}


def detectar(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    out = []
    # 1) Clientes inactivos que podrían volver (Predicción/CRM)
    try:
        from src.services import prediccion
        cl = prediccion.servicio().clientes(emp)
        inact = int((cl.get("clientes") or {}).get("inactivos", 0) or 0)
        if inact >= 3:
            out.append(_opp(
                f"clientes_inactivos_{inact}", "Clientes que podrían volver",
                f"He encontrado algo interesante: {inact} clientes llevan tiempo inactivos. Una "
                "acción de recuperación podría reactivar ventas.",
                prioridad=(P.ALTA if inact >= 10 else P.MEDIA), dominio="comercial",
                por_que="Lo indica el análisis de clientes del motor predictivo (CRM).",
                datos={"clientes_inactivos": inact},
                consecuencias="Ventas recurrentes que hoy no se están capturando.",
                especialistas=["Comercial", "Predicción"], mision="mejorar_ventas"))
    except Exception as e:
        logger.debug("clientes: %s", e)
    # 2) Sobrestock: oportunidad de liberar inmovilizado (Predicción/Inventario)
    try:
        from src.services.ia import adaptadores as A
        exc = A.articulos_exceso(emp)
        if len(exc) >= 5:
            out.append(_opp(
                f"sobrestock_{len(exc)}", "Liberar inmovilizado",
                f"He detectado {len(exc)} artículos con sobrestock. Podríamos liberar inmovilizado "
                "ajustando compras o con una promoción selectiva.",
                prioridad=P.MEDIA, dominio="inventario",
                por_que="Comparación de stock frente a rotación esperada.",
                datos={"articulos_sobrestock": len(exc)},
                consecuencias="Menos capital inmovilizado y menos riesgo de merma.",
                especialistas=["Inventario", "Compras"], mision="reducir_costes"))
    except Exception as e:
        logger.debug("sobrestock: %s", e)
    # 3) Oportunidad por TEMPORADA (contexto temporal)
    m = temporal.momento()
    if m["periodo"] in ("navidad", "rebajas"):
        out.append(_opp(
            f"campana_{m['periodo']}", "Campaña recomendable",
            f"{temporal.matiz(m)}creo que sería buen momento para preparar una campaña comercial y "
            "aprovechar el aumento de demanda.",
            prioridad=P.ALTA, dominio="comercial",
            por_que=f"Estamos en periodo de {m['periodo']}, con mayor propensión a la compra.",
            datos={"periodo": m["periodo"]},
            consecuencias="Aprovechar el pico de demanda estacional.",
            especialistas=["Comercial", "Simulación"], mision="mejorar_ventas"))
    return out
