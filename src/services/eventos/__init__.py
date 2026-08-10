"""
Motor Corporativo de Eventos (Fase 1) — API interna unica del Event Bus.

Uso desde cualquier modulo (SIN conocer la implementacion de otros modulos):

    from src.services import eventos
    eventos.publicar("MERMA_REGISTRADA", ref_entidad="merma", ref_id=merma_id,
                     payload={"codigo": cod, "cantidad": q})

Caracter observacional en la Fase 1: se publican y persisten, nadie los consume aun.
"""

from src.services.eventos import estados, prioridades, tipos          # noqa: F401
from src.services.eventos.bus import (archivar, buscar, cancelar,     # noqa: F401
                                      consumir, desuscribir, historial,
                                      metricas, obtener, publicar,
                                      reintentar, suscribir)

__all__ = [
    "publicar", "suscribir", "desuscribir", "consumir", "buscar", "obtener",
    "cancelar", "reintentar", "archivar", "historial", "metricas",
    "estados", "prioridades", "tipos",
]
