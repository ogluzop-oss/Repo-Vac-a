"""
DIRECCIÓN de operaciones digital de SOMA (Fase 7). Fachada de la AUTONOMÍA EMPRESARIAL SUPERVISADA:
SOMA detecta situaciones (riesgos y oportunidades), genera objetivos de negocio razonados y PROPONE
iniciativas priorizadas ANTES de que el usuario pregunte — pero NUNCA ejecuta nada por su cuenta.

Contrato de gobierno (invariante):
  · SOMA propone, observa, razona, prioriza y explica.
  · Toda ejecución sigue pasando por Workflow, Gobierno y Autonomía Supervisada.
  · Solo prioridades CRÍTICA/ALTA justifican una auto-invocación; el resto va a la BANDEJA.

Reutiliza (sin duplicar): razonamiento (Fase 4), Prediction/Gemelo/KPIs/Workflow/Auditoría, el
Mission Engine (Fase 6) y los Especialistas IA (AgentManager). Todo el trabajo es de fondo.
"""

import logging

from src.soma import prioridad as P
from src.soma.direccion import iniciativas
from src.soma.direccion.bandeja import bandeja

logger = logging.getLogger("soma.direccion")


def analizar(id_empresa=None, *, usuario=None) -> list:
    """Genera todas las iniciativas (riesgos + oportunidades + objetivos) priorizadas y explicables."""
    try:
        return iniciativas.generar(id_empresa, usuario=usuario)
    except Exception as e:
        logger.debug("analizar: %s", e)
        return []


def generar_y_priorizar(id_empresa=None, *, usuario=None):
    """Analiza, VUELCA todo en la bandeja de sesión y devuelve (top_intervencion, todas).

    `top_intervencion` es la primera iniciativa que merece interrumpir (CRÍTICA/ALTA) o None. La GUI
    la usa para una posible auto-invocación; el resto queda consultable en la bandeja.
    """
    todas = analizar(id_empresa, usuario=usuario)
    try:
        bandeja().añadir_muchas(todas)
    except Exception as e:
        logger.debug("bandeja: %s", e)
    top = next((i for i in todas if P.merece_intervencion(i.get("prioridad", P.MEDIA))), None)
    return top, todas


def explicar(ini) -> str:
    return iniciativas.explicar(ini)
