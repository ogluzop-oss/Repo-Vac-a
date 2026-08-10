"""
Aplicador de cambios replicados (Fase 4, SUBFASE 4.2). Idempotente y version-aware.
"""

import logging

logger = logging.getLogger("replicacion.aplicador")

# entidad (ref_entidad del evento) -> funcion aplicadora fn(cambio, id_empresa) -> None
_APLICADORES = {}


def registrar_aplicador(entidad, fn) -> None:
    """Registra el aplicador concreto de una entidad (articulos, precios, clientes, stock...)."""
    _APLICADORES[str(entidad)] = fn


def aplicadores_registrados() -> list:
    return sorted(_APLICADORES.keys())


def aplicar(cambio: dict, id_empresa=None) -> str:
    """Aplica un cambio replicado. Devuelve 'aplicado' | 'omitido' | 'error'."""
    ent = str(cambio.get("ref_entidad") or "")
    rid = cambio.get("ref_id")
    try:
        fn = _APLICADORES.get(ent)
        if fn:
            fn(cambio, id_empresa)   # aplicacion concreta del dominio (nodo remoto real)
        # Version-aware: registra la version replicada de la entidad (base para consistencia).
        if ent and rid is not None:
            from src.services.distribucion import versionado
            versionado.registrar_version(ent, rid, autor=cambio.get("usuario"),
                                         origen=cambio.get("origen"), payload=cambio.get("payload"),
                                         id_empresa=id_empresa)
        return "aplicado"
    except Exception as e:
        logger.error("aplicar cambio %s:%s -> %s", ent, rid, e)
        return "error"
