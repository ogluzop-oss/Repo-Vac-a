"""
GraphQL Enterprise · Subscriptions (Fase IV · Bloque 1) — ARQUITECTURA PREPARADA (sin tiempo real
todavía). Mapea tipos de evento del Corporate Event Bus a canales GraphQL:

    Event Bus  →  Subscriptions  →  clientes GraphQL

No abre websockets ni push todavía: declara los canales y, cuando se active el tiempo real, cada
subscription se alimentará del MISMO Event Bus (nunca un bus paralelo). `puente(nombre, publicar)`
deja listo el enganche: suscribe el canal al Event Bus y reenvía al transporte que se le indique.
"""

from __future__ import annotations

from src.api.graphql import registry

# Canales previstos: nombre GraphQL → tipo de evento del Corporate Event Bus.
_CANALES = {
    "onCommunicationSent": "CommunicationSent",
    "onCommunicationFailed": "CommunicationFailed",
    "onCampaignProgress": "CampaignProgress",
    "onPluginInstalled": "PluginInstalled",
    "onPluginRemoved": "PluginRemoved",
    "onWorkflowStep": "WorkflowStepExecuted",
    "onRuleTriggered": "RuleTriggered",
}


def registrar_todo():
    for canal, evento in _CANALES.items():
        registry.registrar_subscription(canal, evento, tipo="JSON")


def puente(nombre, publicar):
    """Engancha (PREPARADO) un canal al Event Bus: cuando llegue su evento, invoca `publicar(payload)`.
    Devuelve True si quedó suscrito. No hay entrega en tiempo real aún; deja el cableado listo."""
    sub = registry.subscriptions().get(nombre)
    if not sub:
        return False
    try:
        from src.services import eventbus

        def _handler(evento):
            try:
                publicar(getattr(evento, "payload", evento))
            except Exception:
                pass
        eventbus.subscribe(sub["evento"], _handler)
        return True
    except Exception:
        return False


__all__ = ["registrar_todo", "puente"]
