"""
Especialistas IA de SOMA (Fase 1 — núcleo).

El sistema OFICIAL de capacidades de SOMA es el **AgentManager** existente (`src/services/agentes`),
que pasa a denominarse "Especialistas IA". NO se introduce un concepto nuevo de "Skills" ni un
registro paralelo: toda capacidad futura se registra como un Especialista IA (un agente por dominio)
en el AgentManager. Este módulo es solo un ACCESOR semántico al sistema oficial.
"""

import logging

logger = logging.getLogger("soma.especialistas")


def sistema():
    """Devuelve el AgentManager oficial (sistema de Especialistas IA)."""
    from src.services.agentes import manager
    return manager()


def dominios() -> list:
    """Lista de dominios cubiertos por los Especialistas IA registrados."""
    try:
        mgr = sistema()
        doms = []
        for a in mgr.agentes():
            doms.extend(getattr(a, "dominios", ()))
        return sorted(set(doms))
    except Exception as e:
        logger.debug("dominios especialistas: %s", e)
        return []
