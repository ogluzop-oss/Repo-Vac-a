"""
Corporate Event Bus (Fase III · B1) — fachada pública.

    from src.services import eventbus
    eventbus.publish("CommunicationSent", id_empresa=..., ref_entidad="comunicacion", ref_id=com_id)
    eventbus.subscribe("InvoicePaid", handler)
    eventbus.replay(tipo="CommunicationSent", id_empresa=...)

Envuelve el bus existente (`services.eventos`) sin reescribirlo. API-First (sin PyQt).
"""

from src.services.eventbus.eventbus import (  # noqa: F401
    publish, subscribe, unsubscribe, replay, catalogo, registrar_evento, suscripciones,
)
from src.services.eventbus import event_registry as event_registry  # noqa: F401
from src.services.eventbus import serializer as serializer  # noqa: F401

__all__ = ["publish", "subscribe", "unsubscribe", "replay", "catalogo", "registrar_evento",
           "suscripciones", "event_registry", "serializer"]
