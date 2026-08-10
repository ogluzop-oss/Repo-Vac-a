"""
Plataforma de Comercio Digital (PCD) — fachada de servicios (Fase 1 · scaffolding).

Ensamblaje sobre la infraestructura Enterprise (RFC-CD-000…006, congelados por N11/N12). La PCD
depende SOLO de la fachada de capacidades (`platform.capabilities`), publica sus contratos para que
la Enterprise Platform los registre (aislamiento del Service Registry) y consume/publica por el
Event Bus. Sin lógica de negocio todavía: cada subservicio es un esqueleto que se completa en su fase.

    from src.services import comercio_digital as cd
    cd.descriptor()            # estado de todos los subservicios
    cd.contratos()             # ServiceContract[] (los registra platform.bootstrap)
"""

from src.services.comercio_digital import (  # noqa: F401
    automatizacion, canales, catalogo, checkout, comercial, conexiones, envios, gobernanza,
    inventario, pagos, presencia, publicaciones, sync, transacciones,
)

VERSION = "1.8.0"   # Etapa B · Fase B8 (Automatización comercial: feeds/republicación/SEO/campañas)
FASE_ACTUAL = 10    # Etapa A completa (0-10)
ETAPA_B_FASE = 8

# Subservicios (nombre lógico → módulo con descriptor()).
_SUBSERVICIOS = {
    "cd_transacciones": transacciones,
    "cd_inventario": inventario,
    "cd_publicaciones": publicaciones,
    "cd_canales": canales,
    "cd_presencia": presencia,
    "cd_sync": sync,
    "cd_checkout": checkout,
    "cd_conexiones": conexiones,
    "cd_catalogo": catalogo,
    "cd_comercial": comercial,
    "cd_pagos": pagos,
    "cd_envios": envios,
    "cd_automatizacion": automatizacion,
}

# Declaración de contratos (capacidades/transportes/dependencias/rutas). Los DEPENDS apuntan a
# servicios ya registrados por la Enterprise Platform (reutilización; N7). health=None en scaffolding.
_CONTRATOS = [
    ("comercio_digital", ("comercio", "omnicanal"), ("rest", "graphql", "eventbus"),
     ("rest_api", "graphql", "eventbus"), ("/commerce",)),
    ("cd_transacciones", ("transacciones",), ("rest", "graphql", "eventbus"),
     ("workflow", "eventbus", "ccp"), ("/commerce/transactions",)),
    ("cd_inventario", ("availability", "fulfillment", "reservas"), ("rest", "eventbus"),
     ("rules", "scheduler"), ("/commerce/availability", "/commerce/fulfillment")),
    ("cd_publicaciones", ("publicaciones",), ("rest", "graphql"), ("marketplace",),
     ("/commerce/publications",)),
    ("cd_canales", ("canales", "adaptadores"), ("rest", "eventbus"), ("marketplace",),
     ("/commerce/channels",)),
    ("cd_presencia", ("presencia_digital",), ("rest",), ("agents_platform", "observability"),
     ("/commerce/presence",)),
    ("cd_sync", ("sincronizacion",), ("eventbus",), ("scheduler", "eventbus"), ("/commerce/sync",)),
    ("cd_checkout", ("checkout",), ("rest", "eventbus"), ("eventbus",), ("/commerce/checkout",)),
]


def contratos() -> list:
    """ServiceContract[] que la Enterprise Platform registrará (la PCD no toca el Service Registry).
    El contrato agregado expone `health` (Observabilidad, Fase 9) reutilizando la gobernanza."""
    from src.platform.contracts import ServiceContract
    out = []
    for (n, caps, trans, deps, rutas) in _CONTRATOS:
        health = gobernanza.salud if n == "comercio_digital" else None
        out.append(ServiceContract(nombre=n, version=VERSION, capacidades=caps, transportes=trans,
                                   dependencias=deps, rutas=rutas, health=health))
    return out


def descriptor() -> dict:
    subs = {n: m.descriptor() for n, m in _SUBSERVICIOS.items()}
    estados = {s.get("estado") for s in subs.values()}
    if estados == {"implementado"}:
        estado = "operativo"
    elif estados == {"scaffolding"}:
        estado = "scaffolding"
    else:
        estado = "en_progreso"
    return {"plataforma": "Comercio Digital", "version": VERSION, "fase": FASE_ACTUAL,
            "estado": estado, "capacidades": _cap_descriptor(), "subservicios": subs,
            "gobernanza": gobernanza.descriptor()}


def _cap_descriptor():
    try:
        from src.platform import capabilities as cap
        return cap.descriptor()
    except Exception:
        return {}


__all__ = ["VERSION", "contratos", "descriptor", "transacciones", "inventario", "publicaciones",
           "canales", "presencia", "sync", "checkout", "gobernanza", "conexiones", "catalogo",
           "comercial", "pagos", "envios", "automatizacion"]
