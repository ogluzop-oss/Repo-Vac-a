"""
Automatizaciones de la CCP (Parte I) — puntos de extensión PREPARADOS (sin implementar).

Deja el hueco para recordatorios, avisos automáticos, envíos programados, bots, agentes IA y workflow,
que a futuro podrán solicitar comunicaciones a través del Corporate Communication Service. Hoy es solo
un registro no-op: registrar una automatización no dispara nada todavía.
"""

import logging

logger = logging.getLogger("ccp.automatizaciones")

_AUTOMATIZACIONES: dict = {}


def registrar_automatizacion(clave, fn, *, descripcion=None):
    """Registra una automatización (recordatorio/programado/bot/workflow). Preparado: no se ejecuta
    nada automáticamente en esta fase; solo queda catalogada para el futuro motor."""
    _AUTOMATIZACIONES[clave] = {"fn": fn, "descripcion": descripcion}
    return clave


def automatizaciones() -> dict:
    return dict(_AUTOMATIZACIONES)
