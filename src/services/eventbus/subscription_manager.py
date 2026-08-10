"""
Subscription Manager (Fase III · B1) — gestión de suscripciones sobre el bus existente.

Envuelve `services.eventos.bus.suscribir/desuscribir` y lleva registro de las suscripciones activas
(para introspección/telemetría). No reimplementa el despacho: reutiliza el del bus.
"""

import logging

logger = logging.getLogger("eventbus.subs")

_SUBS: dict = {}   # tipo → set(handlers)


def subscribe(tipo, handler) -> bool:
    try:
        from src.services.eventos import bus
        bus.suscribir(tipo, handler)
        _SUBS.setdefault(tipo, set()).add(handler)
        return True
    except Exception as e:
        logger.debug("subscribe(%s): %s", tipo, e)
        return False


def unsubscribe(tipo, handler) -> bool:
    try:
        from src.services.eventos import bus
        bus.desuscribir(tipo, handler)
        _SUBS.get(tipo, set()).discard(handler)
        return True
    except Exception as e:
        logger.debug("unsubscribe(%s): %s", tipo, e)
        return False


def suscripciones(tipo=None) -> dict:
    if tipo:
        return {tipo: list(_SUBS.get(tipo, set()))}
    return {t: list(hs) for t, hs in _SUBS.items()}
