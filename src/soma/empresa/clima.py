"""
PERSONALIDAD ADAPTATIVA (Fase 8). SOMA sigue siendo PROFESIONAL — nunca infantil, nunca finge
emociones — pero adapta ligeramente su comunicación al 'clima' de trabajo del día: mucha carga,
tranquilidad o buenas noticias. Solo transmite cercanía profesional. No modifica la personalidad
existente (Fase 3): añade un matiz de contexto que usan los mensajes de continuidad.
"""

import logging

from src.soma import prioridad as P

logger = logging.getLogger("soma.empresa.clima")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def clima(id_empresa=None) -> dict:
    """Devuelve {nivel, matiz}. nivel ∈ carga|buenas_noticias|estable|normal. Best-effort y sutil."""
    emp = _emp(id_empresa)
    criticos = _criticos_en_bandeja()
    mejora = _tendencia_mejora(emp)

    if criticos >= 3:
        return {"nivel": "carga",
                "matiz": "Hoy tienes bastante carga; intentaré ayudarte todo lo posible. "}
    if mejora is True:
        return {"nivel": "buenas_noticias",
                "matiz": "Buenas noticias: las previsiones han mejorado respecto a antes. "}
    if criticos == 0:
        return {"nivel": "estable", "matiz": "Todo está bastante estable hoy. "}
    return {"nivel": "normal", "matiz": ""}


def _criticos_en_bandeja() -> int:
    try:
        from src.soma.direccion.bandeja import bandeja
        items = bandeja().listar(limite=20)
        return len([i for i in items if P.merece_intervencion(i.get("prioridad", "MEDIA"))])
    except Exception as e:
        logger.debug("criticos: %s", e)
        return 0


def _tendencia_mejora(emp):
    """True si un KPI de referencia mejora respecto al periodo anterior; None si no hay dato."""
    try:
        from src.soma.empresa import historico
        t = historico.comparar("ventas", id_empresa=emp)
        if t and t.get("tendencia") in ("sube", "baja"):
            return t["tendencia"] == "sube"
    except Exception as e:
        logger.debug("tendencia: %s", e)
    return None
